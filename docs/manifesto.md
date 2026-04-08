# Manifesto

## The Problem

Every AI coding session starts from zero.

You spend an hour working with Claude. You make decisions. You solve problems. You discover that Zustand breaks in a weird way with Next.js App Router, so you switch to Jotai. You figure out that the auth migration has to run before the role migration, not after. You decide the cache TTL should be 300 seconds because of a specific edge case in the upstream API.

Then the chat hits its context limit, or you close the laptop, or you open a new file in a new conversation.

**Everything you just learned is gone.**

The next session, Claude doesn't remember the Zustand problem. It suggests Zustand. You re-explain. It doesn't remember the migration order. You re-explain. It doesn't remember the cache TTL reasoning. You re-explain.

You are the memory. You are the bridge. You are the thing that should not have to exist.

This is not a small problem. It is the single largest tax on AI-assisted software development. It silently multiplies the cost of everything. It turns every new chat into a re-onboarding. It punishes the very practice of reaching for AI help, because the more you use it, the more context you have to re-transmit.

## Why Existing Solutions Fail

**Summarization-based memory** (most "memory" features in chat tools) compresses your session into a paragraph. The paragraph loses the specifics. The specifics were the entire value. When you ask "why did we switch from Zustand to Jotai" the summary says "state management decisions were discussed" and you are exactly as lost as before.

**Prompt-based memory** (copy-paste context into every new chat) makes you the janitor. It scales with willpower, and willpower is finite.

**Vector memory without taxonomy** (dump everything into a single embedding store) sounds smart and performs at ~60% recall because nearest-neighbor search without metadata filters is noise.

**Tool-based memory** (write notes to files) depends on you remembering to write, and on the next session remembering to read. Both of those are the thing we were supposed to fix.

## What Actually Works

**Verbatim storage.** Keep the original text. Do not summarize. Storage is cheap. Your future self needs the exact words you used, not a paraphrase.

**Structured taxonomy.** Organize memories by project (wing), topic (room), and entry (drawer). Retrieval with wing+room metadata filters jumps from ~60% to ~95% recall. This is not theory — it's [MemPalace](https://github.com/milla-jovovich/mempalace)'s measured result on LongMemEval.

**Layered retrieval.** Not every memory is equally relevant. Load identity (who am I working with) and essential facts (what project is this) every session. Load on-demand memories when the conversation touches them. Load deep memories only when explicitly searched. Four layers, not one.

**Automatic capture, automatic restore.** The user should not type `init` or `wrapup`. A daemon should watch the conversation and capture it. The next session should restore context without being asked. Ceremony is where users drop out.

**Observable memory.** You should always be able to ask "what do you remember about this project?" and get a real answer. Not "I remember everything" (a lie) or "I don't have access to prior conversations" (also a lie). A list. With dates. With content.

Cairntir does all five.

## The Bigger Mission

Cairntir is the memory layer. But memory layers matter because of what they enable on top.

The road Cairntir is on leads to **AI + grand-scale 3D printing + post-scarcity tooling**.

Think about it. Today, AI can model anything. Tomorrow, AI can print anything. The day after that, the cost of making a thing approaches zero. The thing that was scarce was never the atoms — it was the design, the iteration, the knowledge of what works. The knowledge of what the last person tried and why it failed. **The memory.**

A machine that prints its own thingamajigs needs to remember which thingamajig worked. Which material. Which temperature. Which grain direction. Which iteration was the one that finally solved it. Otherwise every print is an isolated experiment and nothing compounds.

When compounding is possible, the math flips. A thingamajig that makes more thingamajigs, for nearly free, given away — that is post-scarcity. We are not far from it. What we are missing is the memory layer that lets the knowledge compound across iterations, across machines, across users, across time.

Cairntir is a tiny early draft of that layer. Today it remembers code decisions. Tomorrow it remembers print results. Eventually it remembers the things a whole civilization of makers needs to remember so that nothing good is ever accidentally lost.

## The Promise

Cairntir will be **free**, **open source** (MIT), **local-first**, and **opinionated**. It will never become a SaaS. It will never gate features behind a subscription. It will never harvest your data. It will never require a network connection to remember what you did yesterday.

It will be small enough to audit. It will fail loudly instead of silently. It will expose its memory to you, not hide it behind hand-waving.

If it works, it will quietly become the thing you forget you're using, because the amnesia stops happening and you stop noticing its absence. That is the highest compliment software can earn.

If it doesn't work, the author will still have tried. That matters too.

---

*Cairntir is step one. The road is long. The road is worth walking.*
