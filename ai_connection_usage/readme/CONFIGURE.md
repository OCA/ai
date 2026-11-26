In Settings > Technical > AI > AI Connection, open a connection:

- set its Company, or leave it empty to count each call against the current
  company of the user;
- in the Usage tab, set the price currency, the input and output prices per
  million tokens, the optional monthly cap of the connection, and whether
  prompts and answers are kept in the log.

The monthly cap of a company is set on the company form (AI Monthly Spending
Cap, in the company currency). Zero means no cap.

Only administrators (Settings) can see and change prices, caps and the
stored prompts and answers.

The day of each call, and so the month the caps count, is taken in the
timezone of the system parameter `ai_connection_usage.timezone` (for example
`America/Argentina/Buenos_Aires`); UTC when it is not set.
