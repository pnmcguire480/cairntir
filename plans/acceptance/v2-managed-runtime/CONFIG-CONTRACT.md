# CLI configuration replacement supplement v1

The frozen core protocol explicitly says replacement of executable/config invalidates readiness, and the parent required rereading trusted configuration before launch. The first candidate rereads executable bytes but its CLI only reads the configuration file at startup. This separately frozen case tests that existing requirement with a real CLI process and an owned production cache copy.

After capture, complete brief, and matching acknowledgement, change only the configured profile's output_limit_bytes in the same --config file. An action submitted using the old acknowledgement must return a structured error and create no child marker. No action may run using stale configuration. Refusing the current worker until explicit restart with the new config is sufficient; hot reload is not required. The module constructor's detached dictionary stays immutable; the file reread/binding is a CLI boundary responsibility. Rejecting replacement also applies when the new file is invalid or unavailable.

This does not claim race-free executable replacement against a privileged same-user adversary or an OS isolation boundary. It is an observable managed protocol configuration check before dispatch. The original successful real-CLI case is the positive control. Original freezes and source remain unchanged.
