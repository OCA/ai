As an administrator access `AI Bridge\AI Bridge`.

Create a new bridge.
Define the name, model, url and configuration.

In order to improve the view of the AI configuration, use groups and domain to set better filters.

## Payload Configuration

On the external system, you will receive a POST payload. The data included will be the following:

### General

- _odoo: Standard data to identify the Odoo Database
- _model: Model of the related object
- _id: Id of the related object
- _response_url: Url to call with the response in case of async calls

### Record Payload


Adds a new item called record with all the fields.

### Record Payload (v0)

Adds all the fields directly on the payload.
It will be removed on 17.0.

## Asynchronous and synchronous calls

The new system allows asynchronous and synchronous calls. 
Asynchronous calls makes sense when the task to be processed don't need to be immediate.
For example, reviewing an invoice and leave a comment with the result.
The same would happen with a chat message.
We expect that the system will leave time to the AI to answer and Odoo's user can do other things.

Meanwhile, Synchronous calls will froze odoo system and wait for an answer.
This makes sense when we expect some feedback from odoo user.
It makes sense, when we open an action for example.

In the synchronous call, the result is processed when the AI system answers on the webhook.
On the other hand, it will be processed automatically on the synchronous call.

## Result processing

With the answers of the system we expect to do something about it.
We have the following options:

### No processing

In this case, the result will do nothing

### Post a Message

We will post a message on the original thread of the system.
The thread is computed by a function, so it can be overriden in future modules.
It expects the keyword arguments of the `message_post` function.

### Action

It expects to launch an action on the user interface.
It only makes sense on synchronous calls.

It expects an action item with the following parameters:

- action: xmlid of the action
- context: Context to pass to the action (not required)
- res_id: Id of the resource (not required)