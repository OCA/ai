/*
    Copyright 2025 Dixmit
    License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
*/
import {AiBridge} from "./mock_models/ai_bridge.esm";
import {defineModels} from "@web/../tests/web_test_helpers";
import {mailModels} from "@mail/../tests/mail_test_helpers";
export const baseAIModels = {
    AiBridge,
};

export function defineBaseAIModels() {
    return defineModels({...mailModels, ...baseAIModels});
}
