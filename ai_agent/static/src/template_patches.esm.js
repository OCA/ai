import {AgentContextBar} from "./components/agent_context_bar.esm";
import {AgentDraft} from "./components/agent_draft.esm";
import {AgentSidebar} from "./components/agent_sidebar.esm";
import {AI_AGENTS_CATEGORY_ID} from "./model_patches.esm";

import {ChatWindow} from "@mail/core/common/chat_window";
import {threadActionsRegistry} from "@mail/core/common/thread_actions";
import "@mail/discuss/core/common/thread_actions";
import {Discuss} from "@mail/core/public_web/discuss";
import {DiscussSidebarCategories} from "@mail/discuss/core/public_web/discuss_sidebar_categories";

import {useState} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";

Object.assign(Discuss.components, {AgentContextBar, AgentDraft});
patch(Discuss.prototype, {
    setup() {
        super.setup(...arguments);
        this.aiAgentState = useState(useService("ai_agent").state);
    },
    get aiAgentDraft() {
        return !this.thread && this.aiAgentState.draft;
    },
    get aiAgentDraftAgent() {
        return this.aiAgentState.agents.find(
            (agent) => agent.id === this.aiAgentDraft?.agentId
        );
    },
});

Object.assign(ChatWindow.components, {AgentContextBar, AgentDraft});

Object.assign(DiscussSidebarCategories.components, {AgentSidebar});
patch(DiscussSidebarCategories.prototype, {
    get aiAgentsCategoryId() {
        return AI_AGENTS_CATEGORY_ID;
    },
});

// AI agent conversations are private to the user and the agent
const inviteAction = threadActionsRegistry.get("invite-people");
const inviteCondition = inviteAction.condition;
inviteAction.condition = (component) =>
    component.thread?.channel_type !== "ai_agent" && inviteCondition(component);
