import {AgentSidebar} from "./agent_sidebar.esm";
import {getCurrentViewContext} from "../view_context.esm";

import {Component, useState} from "@odoo/owl";
import {Dropdown} from "@web/core/dropdown/dropdown";
import {useDropdownState} from "@web/core/dropdown/dropdown_hooks";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

/**
 * The AI agents from anywhere in the backend: new conversations about the
 * view the user is looking at, and the last ones, in chat windows.
 */
export class AgentSystrayMenu extends Component {
    static template = "ai_agent.AgentSystrayMenu";
    static components = {AgentSidebar, Dropdown};
    static props = {};

    setup() {
        this.aiAgent = useService("ai_agent");
        this.agents = useState(this.aiAgent.state);
        this.dropdown = useDropdownState();
    }

    getContext() {
        const context = getCurrentViewContext(this.env);
        if (!context) {
            return {};
        }
        return {
            resModel: context.resModel,
            resId: context.resId,
            resName: context.resId ? undefined : context.viewContext.action_name,
            viewContext: context.viewContext,
        };
    }
}

registry
    .category("systray")
    // Between the debug menu (100) and the messaging menu (25)
    .add("ai_agent.AgentSystrayMenu", {Component: AgentSystrayMenu}, {sequence: 50});
