/*
    Copyright 2025 Dixmit
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/
import {fields, models} from "@web/../tests/web_test_helpers";

export class AiBridge extends models.ServerModel {
    _name = "ai.bridge";
    result_type = fields.Selection({
        selection: [
            ["none", "None"],
            ["action", "Action"],
            ["notification", "Notification"],
        ],
        default: "none",
    });
    name = fields.Char();
    _records = [
        {id: 1, name: "Test AI Bridge", result_type: "none"},
        {id: 2, name: "Test AI Bridge Action", result_type: "action"},
    ];
    execute_ai_bridge(ids) {
        const record = this.browse(ids);
        if (record && record[0].result_type === "action") {
            return {
                action: {
                    type: "ir.actions.act_window",
                    res_model: "res.partner",
                    views: [[false, "list"]],
                },
            };
        }
        return {
            notification: {
                body: "Mocked AI Bridge Response",
                args: {
                    type: "info",
                    title: "AI Bridge Notification",
                },
            },
        };
    }
}
