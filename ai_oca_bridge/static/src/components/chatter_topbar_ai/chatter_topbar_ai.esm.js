/** @odoo-module **/

import {ChatterAIItem} from "../chatter_topbar_ai_item/chatter_topbar_ai_item.esm";
const {Component} = owl;
import {Dropdown} from "@web/core/dropdown/dropdown";
import {DropdownItem} from "@web/core/dropdown/dropdown_item";
import {registerMessagingComponent} from "@mail/utils/messaging_component";

export class ChatterAITopbar extends Component {
    /**
     * @returns {ChatterAITopbar}
     */
    get chatterTopbar() {
        return this.props.record;
    }
}

Object.assign(ChatterAITopbar, {
    props: {record: Object},
    components: {Dropdown, DropdownItem, ChatterAIItem},
    template: "ai_oca_bridge.ChatterAITopbar",
});

registerMessagingComponent(ChatterAITopbar);
