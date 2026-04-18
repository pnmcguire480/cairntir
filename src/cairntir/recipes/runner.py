"""RecipeRunner — execute a :class:`RecipeContract` end-to-end.

The runner threads four adapters — memory, beliefs, proposer, runner —
through a recipe's declared skill chain, committing a drawer to the
recipe's ``output_wing`` for every skill step plus a seed drawer that
records the inputs and ties subsequent drawers together via
``supersedes_id``.

When the chain includes ``reason``, the runner invokes a real
:class:`~cairntir.reason.ReasonLoop` step with a question derived from
the inputs — the prediction-bound drawer pair the reason loop writes is
the recipe's load-bearing output.

When the chain includes ``crucible`` or ``quality``, the runner writes
a marker drawer embedding the skill text + inputs so the calling LLM
has the skill's prompt in memory to execute against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cairntir.errors import CairntirError
from cairntir.memory.taxonomy import Drawer, Layer
from cairntir.reason.loop import ReasonLoop
from cairntir.skills import load_skill

if TYPE_CHECKING:
    from cairntir.reason.ports import (
        BeliefStore,
        ExperimentRunner,
        HypothesisProposer,
        MemoryGateway,
    )
    from cairntir.recipes.contract import RecipeContract


@dataclass(frozen=True)
class RecipeResult:
    """The outcome of one :class:`RecipeRunner.run` call.

    ``seed_drawer_id`` is the drawer that captured the recipe
    invocation + inputs. ``skill_drawer_ids`` is a per-skill list in
    the order the skills ran; each entry is a list because a single
    skill step may write multiple drawers (the reason loop writes
    two — prediction and observation).
    """

    recipe_name: str
    output_wing: str
    seed_drawer_id: int
    skill_drawer_ids: dict[str, list[int]] = field(default_factory=dict)


class RecipeRunner:
    """Execute a recipe contract with the four reason-loop adapters."""

    def __init__(
        self,
        *,
        memory: MemoryGateway,
        beliefs: BeliefStore,
        proposer: HypothesisProposer,
        runner: ExperimentRunner,
    ) -> None:
        """Bind the four adapters this runner will drive."""
        self._memory = memory
        self._beliefs = beliefs
        self._proposer = proposer
        self._runner = runner

    def run(
        self,
        contract: RecipeContract,
        inputs: dict[str, object],
    ) -> RecipeResult:
        """Validate inputs against ``contract`` and execute the skill chain."""
        _validate_inputs(contract, inputs)

        seed_drawer = Drawer(
            wing=contract.output_wing,
            room=_canonical_room(contract),
            content=_format_seed_content(contract, inputs),
            layer=Layer.ON_DEMAND,
            metadata={
                "source": f"recipe.{contract.name}",
                "recipe_version": contract.version,
                "kind": "seed",
            },
        )
        seed_id = self._memory.remember(seed_drawer)

        skill_drawer_ids: dict[str, list[int]] = {}
        for skill in contract.skills:
            if skill == "reason":
                skill_drawer_ids[skill] = self._run_reason(
                    contract, inputs, seed_id=seed_id
                )
            elif skill in ("crucible", "quality"):
                skill_drawer_ids[skill] = [
                    self._run_skill_marker(
                        skill, contract, inputs, seed_id=seed_id
                    )
                ]
            else:  # pragma: no cover — contract.load blocks unknown skills
                raise CairntirError(
                    f"RecipeRunner encountered unknown skill {skill!r} "
                    f"— contract validation should have blocked this"
                )

        return RecipeResult(
            recipe_name=contract.name,
            output_wing=contract.output_wing,
            seed_drawer_id=seed_id,
            skill_drawer_ids=skill_drawer_ids,
        )

    # ------------------------------------------------------------------ skills

    def _run_reason(
        self,
        contract: RecipeContract,
        inputs: dict[str, object],
        *,
        seed_id: int,
    ) -> list[int]:
        """Run a ReasonLoop step seeded with the recipe's inputs.

        Returns [prediction_id, observation_id]. The loop already does
        the work — we just hand it the question.
        """
        loop = ReasonLoop(
            proposer=self._proposer,
            runner=self._runner,
            beliefs=self._beliefs,
            memory=self._memory,
        )
        question = _format_reason_question(contract, inputs)
        update = loop.step(
            question=question,
            wing=contract.output_wing,
            room=_canonical_room(contract),
        )
        # seed_id is recorded in the seed drawer metadata, not as a
        # supersedes pointer — the reason loop uses supersedes for the
        # prediction→observation chain.
        _ = seed_id
        return [update.prediction_id, update.observation_id]

    def _run_skill_marker(
        self,
        skill_name: str,
        contract: RecipeContract,
        inputs: dict[str, object],
        *,
        seed_id: int,
    ) -> int:
        """Write a drawer that marks the skill's slot in the chain.

        The drawer content embeds the skill's markdown prompt so the
        LLM that reads it has the full instructions without a second
        fetch. ``supersedes_id`` points at the seed so
        :func:`~cairntir.memory.temporal.walk_supersedes` can reconstruct
        the recipe's execution arc.
        """
        skill_text = load_skill(skill_name)
        body = (
            f"# Skill: {skill_name} (recipe step for {contract.name})\n\n"
            f"## Inputs\n{_format_inputs(inputs)}\n\n"
            f"## Skill prompt\n{skill_text}\n"
        )
        drawer = Drawer(
            wing=contract.output_wing,
            room=_canonical_room(contract),
            content=body,
            layer=Layer.ON_DEMAND,
            metadata={
                "source": f"recipe.{contract.name}",
                "recipe_version": contract.version,
                "kind": f"skill.{skill_name}",
            },
            supersedes_id=seed_id,
        )
        return self._memory.remember(drawer)


# --------- helpers ------------------------------------------------------


def _validate_inputs(contract: RecipeContract, inputs: dict[str, object]) -> None:
    """Reject missing required inputs and unknown keys."""
    required = contract.required_input_names()
    missing = required - set(inputs)
    if missing:
        raise CairntirError(
            f"recipe {contract.name!r} missing required input(s): {sorted(missing)}"
        )
    for key in inputs:
        spec = contract.input_spec(key)
        if spec is None:
            raise CairntirError(
                f"recipe {contract.name!r} received unknown input {key!r}; "
                f"declared inputs: {[s.name for s in contract.inputs]}"
            )


def _canonical_room(contract: RecipeContract) -> str:
    """Room identifier used for every drawer a recipe writes."""
    # recipe names may contain underscores or other chars that violate
    # the taxonomy regex; normalize to a safe room name.
    name = contract.name
    cleaned = "".join(c if c.isalnum() or c in "-" else "-" for c in name.lower())
    # Trim leading/trailing dashes to satisfy the taxonomy ident regex
    # which requires alnum at the start and end.
    cleaned = cleaned.strip("-")
    return cleaned or "recipe"


def _format_seed_content(
    contract: RecipeContract, inputs: dict[str, object]
) -> str:
    lines = [
        f"# Recipe invocation: {contract.name} v{contract.version}",
        "",
        f"**Description:** {contract.description}",
        f"**Chain:** {' -> '.join(contract.skills)}",
        "",
        "## Inputs",
        _format_inputs(inputs),
    ]
    return "\n".join(lines)


def _format_inputs(inputs: dict[str, object]) -> str:
    if not inputs:
        return "(none)"
    return "\n".join(f"- **{k}:** {v}" for k, v in sorted(inputs.items()))


def _format_reason_question(
    contract: RecipeContract, inputs: dict[str, object]
) -> str:
    """Turn the recipe description + inputs into a question for the proposer."""
    body = _format_inputs(inputs)
    return (
        f"Recipe: {contract.name}\n"
        f"Goal:   {contract.description}\n"
        f"Inputs:\n{body}"
    )
