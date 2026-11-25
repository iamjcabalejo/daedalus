## Configurable idle connections

`common.Init` hard-codes `SetMaxIdleConns(10)`. Read `DB_MAX_IDLE_CONNS` from the environment instead
(default 10; ignore values that are invalid or not positive), and add a unit test for the parsing helper.
Document the variable in `.env.example`.
