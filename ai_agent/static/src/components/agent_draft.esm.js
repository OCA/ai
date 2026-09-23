import {AgentContextBar} from "./agent_context_bar.esm";

import {Component, useRef, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {useAutofocus, useService} from "@web/core/utils/hooks";

/**
 * A new conversation with an agent that does not exist yet: the channel and
 * the session are created when its first message is sent.
 */
export class AgentDraft extends Component {
    static template = "ai_agent.AgentDraft";
    static components = {AgentContextBar};
    static props = {draft: Object, chatWindow: {type: Object, optional: true}};

    setup() {
        this.aiAgent = useService("ai_agent");
        this.agents = useState(this.aiAgent.state);
        this.notification = useService("notification");
        this.state = useState({body: "", sending: false});
        this.textarea = useRef("textarea");
        useAutofocus({refName: "textarea"});
    }

    get agent() {
        return this.aiAgent.getAgent(this.props.draft.agentId);
    }

    get placeholder() {
        return _t("Message %s…", this.agent?.name ?? "");
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
            ev.preventDefault();
            this.send();
        }
    }

    async send() {
        const body = this.state.body.trim();
        if (!body || this.state.sending) {
            return;
        }
        this.state.sending = true;
        try {
            await this.aiAgent.startConversation(
                this.props.draft,
                body,
                this.props.chatWindow
            );
        } catch (error) {
            this.state.sending = false;
            throw error;
        }
    }
}
