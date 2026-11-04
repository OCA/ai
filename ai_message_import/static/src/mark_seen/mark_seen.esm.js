/** @odoo-module **/

import {Component, onWillStart, onWillUpdateProps, xml} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {standardWidgetProps} from "@web/views/widgets/standard_widget_props";
import {useService} from "@web/core/utils/hooks";

/**
 * Marks the document of the form as seen by the user when it is opened, as an
 * email is read when it is opened. It shows nothing.
 */
export class AiMessageMarkSeen extends Component {
    static template = xml``;
    static props = {...standardWidgetProps};

    setup() {
        this.orm = useService("orm");
        this.markedId = false;
        onWillStart(() => this.markSeen(this.props.record));
        onWillUpdateProps((nextProps) => this.markSeen(nextProps.record));
    }

    markSeen(record) {
        if (!record.resId || !record.data.is_new || record.resId === this.markedId) {
            return;
        }
        this.markedId = record.resId;
        // Not awaited: the form does not wait for it.
        this.orm.call(record.resModel, "action_mark_seen", [[record.resId]]);
    }
}

registry.category("view_widgets").add("ai_message_mark_seen", {
    component: AiMessageMarkSeen,
});
