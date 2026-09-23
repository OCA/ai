import {
    click,
    contains,
    insertText,
    openDiscuss,
    openListView,
    start,
    startServer,
    triggerHotkey,
} from "@mail/../tests/mail_test_helpers";

import {describe, expect, test} from "@odoo/hoot";
import {getService, onRpc} from "@web/../tests/web_test_helpers";

import {
    createAgent,
    createAgentChannel,
    defineAiAgentModels,
} from "./ai_agent_test_helpers.esm";

describe.current.tags("desktop");
// The whole web client and Discuss are mounted: leave room for unminified assets
describe.current.timeout(15000);
defineAiAgentModels();

test("the Agents category lists the agents, not their conversations", async () => {
    const pyEnv = await startServer();
    const agent = createAgent(pyEnv);
    createAgent(pyEnv, "Otro");
    createAgentChannel(pyEnv, agent);
    await start();
    await openDiscuss();
    await contains(".o-ai_agent-DiscussSidebarCategory", {text: "Agents"});
    await contains(".o-ai_agent-AgentSidebar-agent", {count: 2});
    await contains(".o-ai_agent-AgentSidebar-agent", {text: "Gemma"});
    // The conversation is under its agent, never in "Direct messages"
    await contains(".o-mail-DiscussSidebarCategory-chat");
    await contains(".o-mail-DiscussSidebarChannel", {
        text: "Capital de Francia",
        count: 0,
    });
    await click(
        ".o-ai_agent-AgentSidebar-agent:contains(Gemma) .o-ai_agent-AgentSidebar-toggle"
    );
    await contains(".o-ai_agent-AgentSidebar-session", {text: "Capital de Francia"});
    await contains(".o-ai_agent-AgentSidebar-more", {text: "Search more…"});
});

test("no Agents category without agents", async () => {
    await startServer();
    await start();
    await openDiscuss();
    await contains(".o-mail-DiscussSidebarCategory-channel");
    await contains(".o-ai_agent-DiscussSidebarCategory", {count: 0});
    await contains(".o-ai_agent-AgentSystrayMenu-toggler", {count: 0});
});

test("a draft becomes a conversation with its first message only", async () => {
    const pyEnv = await startServer();
    createAgent(pyEnv);
    onRpc("ai.agent", "action_start_conversation", ({args}) => {
        expect.step(`start: ${args[1]}`);
    });
    await start();
    await openDiscuss();
    await click(".o-ai_agent-AgentSidebar-new:contains(Gemma)");
    await contains(".o-mail-Discuss-header", {text: "GemmaNew conversation"});
    await contains(".o-ai_agent-AgentDraft");
    expect(
        pyEnv["discuss.channel"].search([["channel_type", "=", "ai_agent"]])
    ).toHaveLength(0);
    await insertText(".o-ai_agent-AgentDraft-input", "¿Cuál es la capital de Francia?");
    await triggerHotkey("Enter");
    await contains(
        ".o-mail-Discuss-threadName[title='¿Cuál es la capital de Francia?']"
    );
    await contains(".o-mail-Message", {text: "¿Cuál es la capital de Francia?"});
    await contains(".o-ai_agent-AgentDraft", {count: 0});
    await contains(".o-ai_agent-AgentSidebar-session.o-active", {
        text: "¿Cuál es la capital de Francia?",
    });
    expect.verifySteps(["start: ¿Cuál es la capital de Francia?"]);
});

test("conversations are private: no invite action", async () => {
    const pyEnv = await startServer();
    const agent = createAgent(pyEnv);
    const channelId = createAgentChannel(pyEnv, agent);
    await start();
    await openDiscuss(channelId);
    await contains(".o-mail-Discuss-threadName[title='Capital de Francia']");
    await contains(".o-mail-Discuss-header button[title='Notification Settings']");
    await contains(".o-mail-Discuss-header button[name='invite-people']", {count: 0});
});

test("the context document is shown in the header", async () => {
    const pyEnv = await startServer();
    const agent = createAgent(pyEnv);
    const partnerId = pyEnv["res.partner"].create({name: "Cliente 42"});
    const channelId = createAgentChannel(pyEnv, agent, {
        ai_res_model: "res.partner",
        ai_res_id: partnerId,
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-ai_agent-AgentContextBar", {text: "Related to:Cliente 42"});
});

test("a view context is shown with its filters and groupings", async () => {
    const pyEnv = await startServer();
    const agent = createAgent(pyEnv);
    const channelId = createAgentChannel(pyEnv, agent, {
        ai_res_model: "res.partner",
        ai_context: {
            action_name: "Contacts",
            view_type: "list",
            facets: ["Name: local"],
            group_by: ["country_id"],
        },
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-ai_agent-AgentContextBar", {
        text: "Related to:Contacts· List· Name: local · Grouped by: country_id",
    });
});

test("agents can not get direct messages: openChat opens a draft", async () => {
    const pyEnv = await startServer();
    const agent = createAgent(pyEnv);
    await start();
    await contains(".o-ai_agent-AgentSystrayMenu-toggler");
    await getService("mail.store").openChat({partnerId: agent.partnerId});
    await contains(".o-mail-ChatWindow .o-ai_agent-AgentDraft");
    await contains(".o-mail-ChatWindow-header", {text: "Gemma"});
    expect(
        pyEnv["discuss.channel"].search([["channel_type", "=", "chat"]])
    ).toHaveLength(0);
});

test("the systray menu starts a conversation about the current view", async () => {
    const pyEnv = await startServer();
    createAgent(pyEnv);
    onRpc("ai.agent", "action_start_conversation", ({kwargs}) => {
        expect.step(`${kwargs.res_model} ${kwargs.view_context.view_type}`);
    });
    await start();
    await openListView("res.partner");
    await contains(".o_list_renderer");
    await click(".o-ai_agent-AgentSystrayMenu-toggler");
    await click(
        ".o-ai_agent-AgentSystrayMenu .o-ai_agent-AgentSidebar-new:contains(Gemma)"
    );
    await contains(".o-mail-ChatWindow .o-ai_agent-AgentDraft");
    await contains(".o-mail-ChatWindow .o-ai_agent-AgentContextBar", {
        text: "Related to:",
    });
    await contains(".o-mail-ChatWindow .o-ai_agent-AgentContextBar", {text: "· List"});
    await insertText(
        ".o-mail-ChatWindow .o-ai_agent-AgentDraft-input",
        "¿Cuántos hay?"
    );
    await triggerHotkey("Enter");
    await contains(".o-mail-ChatWindow .o-mail-Message", {text: "¿Cuántos hay?"});
    await contains(".o-mail-ChatWindow .o-ai_agent-AgentDraft", {count: 0});
    expect.verifySteps(["res.partner list"]);
});

test("search more lists and filters the conversations", async () => {
    const pyEnv = await startServer();
    const agent = createAgent(pyEnv);
    createAgentChannel(pyEnv, agent, {name: "Capital de Francia"});
    createAgentChannel(pyEnv, agent, {name: "Receta de paella"});
    await start();
    await openDiscuss();
    await click(
        ".o-ai_agent-AgentSidebar-agent:contains(Gemma) .o-ai_agent-AgentSidebar-toggle"
    );
    await click(".o-ai_agent-AgentSidebar-more");
    await contains(".o-ai_agent-AgentHistoryDialog-session", {count: 2});
    await insertText(".o-ai_agent-AgentHistoryDialog-search", "paella");
    await contains(".o-ai_agent-AgentHistoryDialog-session", {
        count: 1,
        text: "Receta de paella",
    });
    await click(".o-ai_agent-AgentHistoryDialog-session");
    await contains(".o-mail-Discuss-threadName[title='Receta de paella']");
});
