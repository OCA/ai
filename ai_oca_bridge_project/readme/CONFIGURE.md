- **Bridge with `Usage = "AI Thread Create"`**
    Processes new projects and tasks in the external system for AI-enhanced actions like project analysis, task prioritization, or automated project management.

- **Bridge with `Usage = "AI Thread Write"`**
    Updates project and task information in the external system when they are modified in Odoo.

- **Bridge with `Usage = "AI Thread Unlink"`**
    Removes project and task data from the external system when they are deleted from Odoo.

For creating those bridges, apart from the usage of the bridge, the user must define:
- Payload Type: it depends on the endpoint configuration, normally "Record" would work.
- Result Type: depending on your use case.
- Model: select the "Project" or "Task" model
- Field: add at least the fields the endpoint is expecting (e.g., name, description, stage, assignees, etc.).
- Filter: add a domain for using the bridge only with the projects/tasks intended to trigger automatic actions
