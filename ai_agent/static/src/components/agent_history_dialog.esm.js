import {Component, onWillStart, useState} from "@odoo/owl";
import {Dialog} from "@web/core/dialog/dialog";
import {deserializeDateTime, formatDateTime} from "@web/core/l10n/dates";
import {useService} from "@web/core/utils/hooks";
import {useDebounced} from "@web/core/utils/timing";

const PAGE_SIZE = 20;

/** Every conversation of the user with an agent, searchable. */
export class AgentHistoryDialog extends Component {
    static template = "ai_agent.AgentHistoryDialog";
    static components = {Dialog};
    static props = {agent: Object, close: Function};

    setup() {
        this.aiAgent = useService("ai_agent");
        this.state = useState({term: "", sessions: [], count: 0, loading: true});
        this.onInput = useDebounced(() => this.search(), 300);
        onWillStart(() => this.search());
    }

    async search({append = false} = {}) {
        this.state.loading = true;
        const offset = append ? this.state.sessions.length : 0;
        const result = await this.aiAgent.searchSessions(
            this.props.agent.id,
            this.state.term.trim(),
            offset,
            PAGE_SIZE
        );
        this.state.sessions = append
            ? [...this.state.sessions, ...result.sessions]
            : result.sessions;
        this.state.count = result.count;
        this.state.loading = false;
    }

    formatDate(value) {
        return value ? formatDateTime(deserializeDateTime(value)) : "";
    }

    open(session) {
        this.props.close();
        this.aiAgent.openSession(session);
    }
}
