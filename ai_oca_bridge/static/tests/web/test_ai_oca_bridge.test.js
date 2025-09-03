/*
    Copyright 2025 Dixmit
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/
import {click, queryAll} from "@odoo/hoot-dom";
import {defineModels, fields, models, mountView} from "@web/../tests/web_test_helpers";
import {expect, test} from "@odoo/hoot";
import {defineBaseAIModels} from "../mock_server/define_ai_models.esm";
import {startServer} from "@mail/../tests/mail_test_helpers";

class ResPartner extends models.Model {
    _name = "res.partner";
    ai_bridge_info = fields.Generic({default: []});
}

defineModels([ResPartner]);
defineBaseAIModels();

test("AI Notification", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({
        name: "Awesome partner",
        ai_bridge_info: [
            {id: 1, name: "AI 1", description: "test1 description"},
            {id: 2, name: "AI 2"},
        ],
    });
    await mountView({
        type: "form",
        resId: partnerId,
        resIds: [partnerId],
        resModel: "res.partner",
        arch: `<form>
                <field name="ai_bridge_info" />
                <chatter />
            </form>`,
    });

    await new Promise((resolve) => setTimeout(resolve, 1000));
    await expect(queryAll(".ai_button_selection")).toHaveCount(1, {
        message: "should have an AI button",
    });

    await click(`.ai_button_selection`);
    await new Promise((resolve) => setTimeout(resolve, 1000));
    expect(`.o_ChatterTopbar_AIItem`).toHaveCount(2, {
        message: "should have 2 AI Items",
    });

    await click(`.dropdown-item:first-child`);
    await new Promise((resolve) => setTimeout(resolve, 1000));
    expect(`.o_notification_manager .o_notification`).toHaveCount(1, {
        message: "should have 1 Notification after clicking on AI Item",
    });
});

test("AI Action", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({
        name: "Awesome partner",
        ai_bridge_info: [
            {id: 1, name: "AI 1", description: "test1 description"},
            {id: 2, name: "AI 2"},
        ],
    });
    await mountView({
        type: "form",
        resId: partnerId,
        resIds: [partnerId],
        resModel: "res.partner",
        arch: `<form>
                <field name="ai_bridge_info" />
                <chatter />
            </form>`,
    });

    // We load this view because we need it to be loaded later by the action.
    await mountView({
        type: "list",
        resId: false,
        resIds: [],
        resModel: "res.partner",
        arch: `<list>
                <field name="name"/>
                <field name="active"/>
            </list>`,
    });

    await new Promise((resolve) => setTimeout(resolve, 1000));
    await expect(`.ai_button_selection`).toHaveCount(1, {
        message: "should have an AI button",
    });

    await click(`.ai_button_selection`);
    await new Promise((resolve) => setTimeout(resolve, 1000));
    expect(`.o_ChatterTopbar_AIItem`).toHaveCount(2, {
        message: "should have 2 AI Items",
    });

    await click(`.dropdown-item:nth-child(2)`);
    await new Promise((resolve) => setTimeout(resolve, 1000));
    expect(`.o_list_view`).toHaveCount(1, {
        message: "should have 1 List View after clicking on AI Item with action",
    });
});
