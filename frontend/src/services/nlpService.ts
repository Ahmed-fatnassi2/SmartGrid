import type { NlpResponse } from "../types";
import { api, assertLive } from "./api";

/** French questions -> intent, entities, SPARQL and results (computed by the backend). */
export const nlpService = {
  async ask(question: string): Promise<NlpResponse> {
    assertLive();
    return (await api.post<NlpResponse>("/nlp/ask", { question })).data;
  },
};
