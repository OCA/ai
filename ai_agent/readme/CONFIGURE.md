Create an agent in *AI > Agents*: its user (the one posting the answers),
its AI connection, a system prompt, its tools and the skills to preload
in its system prompt. Other skills added to its tools are loaded by the AI
on demand.

Answers are computed by the *AI Agent: Session Worker* scheduled action,
triggered on every message addressed to an agent. At least one cron
thread/worker is required (`max_cron_threads` greater than 0), otherwise
sessions stay *Queued* forever.

Each iteration of an answer (an AI call and the tools it calls) runs in
its own run of the scheduled action, as a single transaction: the time
limit of the cron jobs (`limit_time_real_cron`) applies to one iteration,
never to a whole answer. A session still running one minute after that
limit lost its job and is marked as failed, with a note in the
conversation. The delay can be changed with the system parameter
`ai_agent.stale_seconds`.

Tools run with the access rights, language and company of the user who
wrote the message.
