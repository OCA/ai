import {AgentHistoryDialog} from "./agent_history_dialog.esm";

import {Component, useState} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

/** Agents of the "Agents" category of the Discuss sidebar. */
export class AgentSidebar extends Component {
    static template = "ai_agent.AgentSidebar";
    static props = {
        // Compact list of the systray menu
        compact: {type: Boolean, optional: true},
        // Context of the new conversations, see AiAgentDraft
        getContext: {type: Function, optional: true},
        // Called after opening something, e.g. to close a dropdown
        onAction: {type: Function, optional: true},
    };

    setup() {
        this.store = useState(useService("mail.store"));
        this.aiAgent = useService("ai_agent");
        this.agents = useState(this.aiAgent.state);
        this.dialog = useService("dialog");
        this.state = useState({expanded: {}});
    }

    isDraftOf(agent) {
        return (
            !this.props.compact &&
            !this.store.discuss.thread &&
            this.agents.draft?.agentId === agent.id
        );
    }

    isActive(session) {
        return Boolean(
            !this.props.compact &&
                session.channel_id &&
                this.store.discuss.thread?.model === "discuss.channel" &&
                this.store.discuss.thread.id === session.channel_id
        );
    }

    isExpanded(agent) {
        return (
            this.state.expanded[agent.id] ??
            agent.sessions.some((session) => this.isActive(session))
        );
    }

    toggle(agent) {
        this.state.expanded[agent.id] = !this.isExpanded(agent);
    }

    newConversation(agent) {
        const context = this.props.getContext?.() ?? {};
        this.aiAgent.openDraft({...context, agentId: agent.id});
        this.props.onAction?.();
    }

    openSession(session) {
        this.aiAgent.openSession(session);
        this.props.onAction?.();
    }

    openHistory(agent) {
        this.dialog.add(AgentHistoryDialog, {agent});
        this.props.onAction?.();
    }
}
