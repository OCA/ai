/** @odoo-module **/

import {Component} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {standardFieldProps} from "@web/views/fields/standard_field_props";

class AiFormBtnWidget extends Component {
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
    }

    async onClickBridge(bridge) {
        const record = this.props.record;
        if (!record.resId) {
            return;
        }
        const result = await this.orm.call("ai.bridge", "execute_ai_bridge", [
            [bridge.id],
            record.resModel,
            record.resId,
        ]);
        if (result && result.action) {
            this.actionService.doAction(result.action);
        } else if (result && result.notification) {
            this.notification.add(result.notification.body, result.notification.args);
        }
    }
}

AiFormBtnWidget.template = "ai_oca_bridge.AiFormBtn";
AiFormBtnWidget.props = {...standardFieldProps};

registry.category("fields").add("ai_form_btn", AiFormBtnWidget);
