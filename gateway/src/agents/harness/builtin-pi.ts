import { createParkerAgentHarness } from "./parker.js";
import type { AgentHarness } from "./types.js";

export function createPiAgentHarness(): AgentHarness {
  return createParkerAgentHarness();
}
