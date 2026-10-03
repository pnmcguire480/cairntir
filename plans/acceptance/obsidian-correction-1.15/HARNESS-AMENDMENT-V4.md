# Scoped transaction facade control

Before repair-1 verification, two independently authored additive cases require
the scoped facade to report the actual transaction state and enforce the same
apply/sync durable boundary as the owner store. They preserve all existing
expectations, and do not replace the original owner transaction failure witnesses.
Version 3 remains under history/v3. This makes 45 active pytest cases: 28 original
Python methods, 15 additive cases, and two mandatory Node cases. No other active
fixture bytes change. These controls complete the finite transaction contract;
further product repair is limited to the original two-round budget.
