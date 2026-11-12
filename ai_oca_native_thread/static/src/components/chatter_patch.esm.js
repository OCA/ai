/* Copyright 2026 Pierre Verkest
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).  */
import {useBus, useService} from "@web/core/utils/hooks";
import {AiThread} from "./ai_thread.esm";
import {Chatter} from "@mail/chatter/web_portal/chatter";
import {patch} from "@web/core/utils/patch";
import {useState} from "@odoo/owl";

function getChatterModelAndId(chatter) {
    const threadModel = chatter.props.threadModel || chatter.props.record?.resModel;
    const threadId = chatter.props.threadId || chatter.props.record?.resId;
    return {threadModel, threadId};
}

function isAiTabInContext(context) {
    if (!context) return false;
    if (typeof context === "string") {
        return (
            context.includes("active_ai_tab") || context.includes("active_ai_thread_id")
        );
    }
    return Boolean(context.active_ai_tab || context.active_ai_thread_id);
}

function isTargetMatch(target, threadModel, threadId) {
    if (!target) return false;
    const matchesModel = !threadModel || target.resModel === threadModel;
    const matchesId = !threadId || target.resId === threadId;
    return matchesModel && matchesId;
}

function getActionContext(actionService) {
    const controller = actionService?.currentController;
    if (!controller) return null;
    return (
        controller.action?.context ||
        controller.userContext ||
        controller.context ||
        null
    );
}

function resolveTargetThread(chatter, actionService) {
    const {threadModel, threadId} = getChatterModelAndId(chatter);
    const target = window.activeAiThreadTarget;
    if (isTargetMatch(target, threadModel, threadId)) {
        return {isAiTab: true, activeThreadId: target.threadId};
    }
    delete window.activeAiThreadTarget;

    const actionContext = getActionContext(actionService);
    const isAiTab = isAiTabInContext(actionContext);
    const targetThreadId =
        typeof actionContext === "object" && actionContext
            ? actionContext.active_ai_thread_id || null
            : null;

    return {isAiTab, activeThreadId: targetThreadId};
}

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        const actionService = useService("action");
        const {isAiTab, activeThreadId} = resolveTargetThread(this, actionService);

        const aiMainTab = isAiTab ? "ai_thread" : this.state?.aiMainTab || "chatter";
        const activeAiThreadId = activeThreadId || this.state?.activeAiThreadId || null;

        if (this.state) {
            this.state.aiMainTab = aiMainTab;
            this.state.activeAiThreadId = activeAiThreadId;
        } else {
            this.state = useState({aiMainTab, activeAiThreadId});
        }

        useBus(this.env.bus, "AI_THREAD:OPEN_THREAD", ({detail}) => {
            const {threadModel, threadId} = getChatterModelAndId(this);
            if (isTargetMatch(detail, threadModel, threadId)) {
                this.state.aiMainTab = "ai_thread";
                this.state.activeAiThreadId = detail.threadId;
            }
        });
    },
});

Chatter.components = {...Chatter.components, AiThread};
