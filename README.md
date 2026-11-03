
[![Support the OCA](https://odoo-community.org/readme-banner-image)](https://odoo-community.org/get-involved?utm_source=repo-readme)

# AI modules for Odoo Instances
[![Runboat](https://img.shields.io/badge/runboat-Try%20me-875A7B.png)](https://runboat.odoo-community.org/builds?repo=OCA/ai&target_branch=18.0)
[![Pre-commit Status](https://github.com/OCA/ai/actions/workflows/pre-commit.yml/badge.svg?branch=18.0)](https://github.com/OCA/ai/actions/workflows/pre-commit.yml?query=branch%3A18.0)
[![Build Status](https://github.com/OCA/ai/actions/workflows/test.yml/badge.svg?branch=18.0)](https://github.com/OCA/ai/actions/workflows/test.yml?query=branch%3A18.0)
[![codecov](https://codecov.io/gh/OCA/ai/branch/18.0/graph/badge.svg)](https://codecov.io/gh/OCA/ai)
[![Translation Status](https://translation.odoo-community.org/widgets/ai-18-0/-/svg-badge.svg)](https://translation.odoo-community.org/engage/ai-18-0/?utm_source=widget)

<!-- /!\ do not modify above this line -->

OCA AI modules let any Odoo database use AI in the way that fits it best:
 
- by **delegating the work to an external AI system** (the *Bridge approach*), or
- by **running it natively inside Odoo** (the *Odoo AI Agent approach*). It also includes the option to access it through MCP system.

Both approaches coexist as separate families of modules, are maintained by the
community, and never lock users into a single AI provider or platform. 

 
## Principles
 
1. **Two approaches, no imposed choice.** Bridge and Odoo AI Agent coexist and are
   kept separate. OCA does not push one way of doing AI.
2. **Vendor-neutral.** No hard dependency on a single AI provider or platform. Open
   or widely adopted standards are preferred (OpenAI-compatible APIs, MCP).
3. **Odoo security always applies.** When AI acts in Odoo, it does so with the
   permissions of a user: access rights and record rules are respected, with no
   silent privilege escalation.
4. **Auditable.** It must be possible to see what was sent, what came back and what
   was done.
5. **Control over data.** Self-hosted and local models, and self-hosted automation
   tools, are first-class use cases. Users decide what data leaves their Odoo.
6. **Small, modular, technical bases.** A technical base module per concern, with
   features and app integrations in separate glue modules, so people install only
   what they need.
7. **Documented.** Every module explains its purpose, configuration and usage in the
   standard OCA readme, and this repository explains how the modules fit together.

### Out of scope
 
- Hosting or training AI models.
- Vendor-specific features in the base modules (these belong in dedicated glue
  modules).

## The two approaches
 
These are two different ways of doing AI in Odoo, not layers of one stack. They
coexist, but they are kept apart.
 
| | **Bridge** | **Odoo AI Agent** |
| --- | --- | --- |
| Where the logic lives | External system (e.g. n8n, a custom service) | Odoo |
| Prompt | Not in Odoo | In Odoo |
| Tools | Defined outside; the external system calls back into Odoo if it needs data | Defined in Odoo (`ai_tool`), using Odoo permissions |
| Status | Mature | Under construction |
| Pros | Light in Odoo; logic can change without upgrading modules; reuse existing automation platforms | Self-contained; permissions and audit are native; no external infrastructure |
| Cons | Prompts and logic are not visible or versioned in Odoo; needs external infrastructure; harder to control what the AI does | More code to maintain in OCA; long-running calls might need a queue |
 
**When to use which?**
 
- Choose the **Bridge** if you already have (or want) an automation or orchestration
  platform such as n8n, and prefer to evolve the AI logic outside Odoo without
  upgrading modules.
- Choose the **Odoo AI Agent** if you want prompts, tools, permissions and audit to
  live inside Odoo, with no extra infrastructure.
- You can use **both** in the same database.

**MCP.** Odoo tools (`ai_tool`) can also be exposed to external AI clients (e.g. n8n,
desktop assistants) through the Model Context Protocol (MCP), so external systems can
read and act on Odoo data under per-client keys, with a call log. MCP belongs to the
Odoo AI Agent family of modules.
 
## Glossary
 
| Term | Definition |
| --- | --- |
| **Bridge approach** | Odoo notifies an external system (e.g. n8n or a custom service) and receives a result. The external system does the AI work: prompt, AI connection, tools and logic. Odoo does not hold the prompt. The external system can also call back into Odoo (for example through MCP) to read data or act on it. |
| **Agent approach** | Odoo does the whole action itself: it holds the prompt/instructions, connects to the AI provider and exposes the tools the AI can use. |
| **Bridge** (`ai.bridge`) | Configuration of one call to an external system: when it triggers (usage), what is sent (payload) and what Odoo does with the answer (result type). |
| **Bridge Execution** | One call through a bridge, with its status. |
| **Connection** (`ai.connection`) | Configuration of an AI system (model, temperature, URL). Child modules define the kind (e.g. OpenAI-compatible). It runs the loop of messages and tool calls. Mainly useful for the Agent approach. |
| **Tool** (`ai.tool`) | A function declared with `@aitool` that an AI can call on Odoo data. Defined in Odoo, so relevant to the Agent approach and to MCP. |
| **MCP** | Model Context Protocol, an open standard that lets external AI clients discover and call tools. Used here to expose Odoo tools to external AI systems. |
| **Odoo AI Agent** | A connection + instructions (prompt) + a set of allowed tools. It can then be used from different places (e.g. a server action or a chat). The "Odoo" prefix avoids confusion with agents that live outside Odoo. |
| **AI Thread** | The history of messages between users and the AI. Named *AI Thread* because Odoo already has mail threads. |
| **Context** | The Odoo data sent to the AI or to the external system for a request. |
| **Skill** | A tool that lets us add information and behaviour, and include some extra tools in the system. The skill format used in Odoo 20 ([README](https://github.com/odoo/odoo/blob/20.0/skills/README.md), see also [agentskills.io](https://agentskills.io)) is the reference. *(Under discussion.)* |

## Naming convention
 
Proposed and being confirmed by the AI PSC and contributors:
 
- All modules use the **`ai_oca_`** prefix.
- **Bridge:** `ai_oca_bridge` and `ai_oca_bridge_<feature>`.
- **Odoo AI Agent:** technical bases keep their current names for now (`ai_connection`,
  `ai_connection_openai`, `ai_tool`); New modules should follow the `ai_oca_` prefix (for example
  `ai_oca_<feature>`), without adding a "tool" word to tool modules. After 19, everything will have this naming.
- **Server action:** `ai_automation` keeps its 16.0 name.
- **MCP:** follows the Odoo AI Agent convention. `ai_oca_mcp`

## Chat
 
Bridge and Odoo AI Agent each have their own chat, for different uses; they do not
need to work together.
 
- **Bridge chat:** provided today by `ai_oca_bridge_chatter` using Discuss. A user is
  linked to a bridge, shows as always online, and answers messages (livechat
  included) through the external system.
- **Odoo AI Agent chat:** does not exist yet. A dedicated component (OWL chat with its
  own `ai.thread` model) is the long-term direction, with a UI-independent chat core
  so that Discuss and/or chatter can be added as front-ends. A design note will be
  published for contributor review.

## Share how you use OCA AI
 
We would like to make it easy to share real-world uses of these modules, for example
with the Sales & Marketing Working Group. A short standard file is proposed:
 
- **Problem**
- **Challenge**
- **Customer** (optional)
- **How you solved it with the help of the AI modules**

## Contributing
 
You can help with testing, review, code, documentation or by sharing your use cases.
Open an issue or a pull request on this repository, or join the discussion with the
OCA AI PSC.

<!-- /!\ do not modify below this line -->

<!-- prettier-ignore-start -->

[//]: # (addons)

Available addons
----------------
addon | version | maintainers | summary
--- | --- | --- | ---
[ai_connection](ai_connection/) | 18.0.1.0.0 |  | Creates connections to AI systems
[ai_connection_openai](ai_connection_openai/) | 18.0.1.0.0 |  | Integrate automation with OpenAI/LiteVLLM Api
[ai_oca_bridge](ai_oca_bridge/) | 18.0.2.0.1 |  | Makes a basic configuration to be used as bridge with external AI systems
[ai_oca_bridge_chatter](ai_oca_bridge_chatter/) | 18.0.2.0.0 |  | Integrate a Bridge with a user that will use it on chatter
[ai_oca_bridge_document_page](ai_oca_bridge_document_page/) | 18.0.1.0.0 |  | Adds Documents synchronization using AI Bridges
[ai_oca_bridge_extra_parameters](ai_oca_bridge_extra_parameters/) | 18.0.1.0.1 | <a href='https://github.com/arielbarreiros96'><img src='https://github.com/arielbarreiros96.png' width='32' height='32' style='border-radius:50%;' alt='arielbarreiros96'/></a> | Adds extra parameters to the AI OCA Bridge payload.
[ai_oca_native_generate_ollama](ai_oca_native_generate_ollama/) | 18.0.1.0.0 |  | This module replaces AI from html_editor to use an Ollama server instead of OpenAI through Odoo IAP.
[ai_tool](ai_tool/) | 18.0.1.0.0 |  | We want to generate some specific AI Tools that might be used in other places, like MCP or native.

[//]: # (end addons)

<!-- prettier-ignore-end -->

## Licenses

This repository is licensed under [AGPL-3.0](LICENSE).

However, each module can have a totally different license, as long as they adhere to Odoo Community Association (OCA)
policy. Consult each module's `__manifest__.py` file, which contains a `license` key
that explains its license.

----
OCA, or the [Odoo Community Association](http://odoo-community.org/), is a nonprofit
organization whose mission is to support the collaborative development of Odoo features
and promote its widespread use.
