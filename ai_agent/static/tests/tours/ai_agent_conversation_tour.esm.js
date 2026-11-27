import {registry} from "@web/core/registry";

const QUESTION = "¿Cuál es la capital de Francia?";

/** Wait (up to a minute: real agents are slow) until `check` is true. */
async function waitFor(check, description) {
    const deadline = Date.now() + 60000;
    while (!check()) {
        if (Date.now() > deadline) {
            throw new Error(`Timeout waiting for ${description}`);
        }
        await new Promise((resolve) => setTimeout(resolve, 200));
    }
}

/**
 * New conversation from the "Agents" category of Discuss: the answer of the
 * agent arrives, the conversation gets a generated title, it is listed under
 * its agent and "Search more…" finds it. Works with any agent (the first one).
 */
registry.category("web_tour.tours").add("ai_agent_conversation_tour", {
    steps: () => [
        {
            trigger:
                ".o-ai_agent-AgentSidebar-agent:first .o-ai_agent-AgentSidebar-new",
            run: "click",
        },
        {
            trigger: ".o-ai_agent-AgentDraft-input",
            run: `edit ${QUESTION}`,
        },
        {
            trigger: ".o-ai_agent-AgentDraft-input",
            run: "press Enter",
        },
        {
            trigger: `.o-mail-Discuss-content .o-mail-Message:contains(${QUESTION})`,
            async run() {
                await waitFor(
                    () =>
                        document.querySelectorAll(
                            ".o-mail-Discuss-content .o-mail-Message"
                        ).length >= 2,
                    "the answer of the agent"
                );
            },
        },
        {
            // The provisional title (the question) is replaced by a generated one
            trigger: `.o-ai_agent-AgentSidebar-session.o-active:not(:contains(${QUESTION}))`,
        },
        {
            trigger: ".o-ai_agent-AgentSidebar-sessions .o-ai_agent-AgentSidebar-more",
            run: "click",
        },
        {
            trigger: ".o-ai_agent-AgentHistoryDialog-search",
            run: "edit capital de Francia",
        },
        {
            trigger: ".o-ai_agent-AgentHistoryDialog-session:first",
            run: "click",
        },
        {
            trigger:
                ".o-mail-Discuss-content .o-mail-Message:contains(capital de Francia)",
        },
    ],
});
