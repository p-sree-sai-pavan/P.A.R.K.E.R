import { spawn } from "node:child_process";
import type { AgentHarness } from "./types.js";
import type { EmbeddedRunAttemptResult } from "../pi-embedded-runner/run/types.js";

export function createParkerAgentHarness(): AgentHarness {
  return {
    id: "pi",
    label: "Parker JARVIS Agent",
    supports: () => ({ supported: true, priority: 150 }), // High priority to override default PI harness
    runAttempt: async (params) => {
      return new Promise<EmbeddedRunAttemptResult>((resolve) => {
        // Collect arguments for the bridge
        const inputData = JSON.stringify({
          prompt: params.prompt,
          session_key: params.sessionKey ?? "default_session",
          user_id: "u1" // default user id
        });

        // Use the Python virtual environment's python executable
        const pythonPath = "c:\\Users\\pavan\\Downloads\\disc D\\Projects\\P.A.R.K.E.R\\venv\\Scripts\\python.exe";
        const bridgePath = "c:\\Users\\pavan\\Downloads\\disc D\\Projects\\P.A.R.K.E.R\\parker_bridge.py";
        
        console.error(`[Parker Harness] Spawning bridge: ${pythonPath} ${bridgePath}`);

        const child = spawn(pythonPath, [bridgePath], {
          stdio: ["pipe", "pipe", "pipe"]
        });

        let stdoutData = "";
        let stderrData = "";

        child.stdout.on("data", (chunk) => {
          stdoutData += chunk.toString();
        });

        child.stderr.on("data", (chunk) => {
          stderrData += chunk.toString();
          process.stderr.write(chunk);
        });

        child.on("close", (code) => {
          console.error(`[Parker Harness] Subprocess exited with code ${code}`);
          try {
            if (code !== 0) {
              throw new Error(`Python process exited with code ${code}. Stderr: ${stderrData}`);
            }

            const response = JSON.parse(stdoutData.trim());
            if (response.status === "error") {
              throw new Error(response.error);
            }

            const reply = response.reply || "I didn't catch that, sir.";

            // Trigger openclaw streaming callbacks if present
            if (params.onAssistantMessageStart) {
              params.onAssistantMessageStart();
            }
            if (params.onPartialReply) {
              params.onPartialReply({ text: reply, delta: reply });
            }

            const result: EmbeddedRunAttemptResult = {
              aborted: false,
              externalAbort: false,
              timedOut: false,
              idleTimedOut: false,
              timedOutDuringCompaction: false,
              timedOutDuringToolExecution: false,
              promptError: null,
              promptErrorSource: null,
              sessionIdUsed: params.sessionId,
              messagesSnapshot: [
                { role: "user", content: params.prompt, timestamp: Date.now() },
                { role: "assistant", content: reply, timestamp: Date.now(), api: "openai", provider: "openai", model: "gpt-4", usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 } }
              ] as any[] as any,
              assistantTexts: [reply],
              toolMetas: [],
              lastAssistant: { role: "assistant", content: reply } as any,
              didSendViaMessagingTool: false,
              messagingToolSentTexts: [],
              messagingToolSentMediaUrls: [],
              messagingToolSentTargets: [],
              cloudCodeAssistFormatError: false,
              replayMetadata: { hadPotentialSideEffects: false, replaySafe: true },
              itemLifecycle: { startedCount: 0, completedCount: 0, activeCount: 0 }
            };

            resolve(result);
          } catch (err: any) {
            console.error(`[Parker Harness] Error processing response: ${err.message}`);
            resolve({
              aborted: false,
              externalAbort: false,
              timedOut: false,
              idleTimedOut: false,
              timedOutDuringCompaction: false,
              promptError: err,
              promptErrorSource: "prompt",
              sessionIdUsed: params.sessionId,
              messagesSnapshot: [],
              assistantTexts: ["An error occurred while communicating with Parker."],
              toolMetas: [],
              lastAssistant: undefined,
              didSendViaMessagingTool: false,
              messagingToolSentTexts: [],
              messagingToolSentMediaUrls: [],
              messagingToolSentTargets: [],
              cloudCodeAssistFormatError: false,
              replayMetadata: { hadPotentialSideEffects: false, replaySafe: true },
              itemLifecycle: { startedCount: 0, completedCount: 0, activeCount: 0 }
            });
          }
        });

        // Write the inputs to stdin and close the stream
        child.stdin.write(inputData);
        child.stdin.end();
      });
    }
  };
}
