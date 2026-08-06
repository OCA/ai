/** @odoo-module **/

import {onWillUnmount, onWillUpdateProps} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";
import {FormController} from "@web/views/form/form_controller";

const NOTIFICATION_TYPE = "ai_document_extraction";
const CHANNEL_PREFIX = "ai_document_extraction.move.";

patch(FormController.prototype, {
    setup() {
        this._super(...arguments);
        if (this.props.resModel !== "account.move") {
            return;
        }
        this._aiBusService = useService("bus_service");
        this._aiHandler = this._aiHandler.bind(this);
        this._aiSubscribedResId = null;
        this._aiSubscribe();
        onWillUpdateProps((nextProps) => this._aiSubscribe(nextProps.resId));
        onWillUnmount(() => this._aiUnsubscribe());
    },

    _aiSubscribe(resId = this.props.resId) {
        if (!resId || resId === this._aiSubscribedResId) {
            return;
        }
        this._aiUnsubscribe();
        this._aiSubscribedResId = resId;
        this._aiBusService.addChannel(`${CHANNEL_PREFIX}${resId}`);
        this._aiBusService.subscribe(NOTIFICATION_TYPE, this._aiHandler);
    },

    _aiUnsubscribe() {
        if (!this._aiSubscribedResId) {
            return;
        }
        this._aiBusService.deleteChannel(`${CHANNEL_PREFIX}${this._aiSubscribedResId}`);
        this._aiBusService.unsubscribe(NOTIFICATION_TYPE, this._aiHandler);
        this._aiSubscribedResId = null;
    },

    _aiHandler(payload) {
        if (payload.move_id === this.props.resId) {
            this.model.load();
        }
    },
});
