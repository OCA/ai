/** @odoo-module **/

import {onWillUnmount, useEffect} from "@odoo/owl";
import {FormController} from "@web/views/form/form_controller";
import {patch} from "@web/core/utils/patch";
import {useService} from "@web/core/utils/hooks";

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
        useEffect(
            () => {
                this._aiSyncSubscription(this.model.root?.resId);
            },
            () => [this.model.root?.resId]
        );
        onWillUnmount(() => this._aiUnsubscribe());
    },

    _aiSyncSubscription(resId) {
        if (resId === this._aiSubscribedResId) {
            return;
        }
        this._aiUnsubscribe();
        this._aiSubscribedResId = resId;
        if (!resId) {
            return;
        }
        this._aiBusService
            .addChannel(`${CHANNEL_PREFIX}${resId}`)
            .catch(() => undefined);
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
        if (
            payload.move_id === this.model.root?.resId &&
            !this.model.root?.isInEdition
        ) {
            this.model.load();
        }
    },
});
