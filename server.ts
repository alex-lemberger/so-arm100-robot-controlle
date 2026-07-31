import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI, Type } from "@google/genai";

async function startServer() {
  const app = express();
  app.use(express.json());
  const PORT = 3000;

  // Initialize Gemini API client lazily/safely
  const apiKey = process.env.GEMINI_API_KEY;
  const ai = apiKey ? new GoogleGenAI({
    apiKey,
    httpOptions: {
      headers: {
        'User-Agent': 'aistudio-build'
      }
    }
  }) : null;

  // Health check endpoint
  app.get("/api/health", (req, res) => {
    res.json({
      status: "ok",
      robotModel: "SO-ARM100 (6-DOF)",
      geminiEnabled: !!ai
    });
  });

  // AI Sequence Trajectory Generation Endpoint
  app.post("/api/gemini/generate-sequence", async (req, res) => {
    try {
      const { prompt } = req.body;
      if (!prompt || typeof prompt !== 'string') {
        return res.status(400).json({ error: "Prompt string is required" });
      }

      if (!ai) {
        return res.status(503).json({
          error: "GEMINI_API_KEY environment variable is not configured."
        });
      }

      const response = await ai.models.generateContent({
        model: "gemini-3.6-flash",
        contents: `You are an expert robotics kinematics engineer for the open-source SO-ARM100 (Standardized Open Arm 100) 6-DOF servo arm.
Generate a sequence of keyframes in JSON based on the user request: "${prompt}".

SO-ARM100 Servo limits & defaults:
- base: -180 to +180 deg (0 = center forward)
- shoulder: -90 to +90 deg (0 = upright, + = tilt forward)
- elbow: -120 to +120 deg (0 = straight, + = flex forward)
- wristPitch: -90 to +90 deg (0 = level, + = pitch up, - = pitch down)
- wristRoll: -180 to +180 deg (0 = neutral roll)
- gripper: 0 to 100 % (0 = closed claw, 100 = full open)

Ensure realistic smooth motion timing (durationMs between 600ms and 2000ms).
Create 3 to 7 logical step keyframes. Always end in a safe rest posture or completed goal pose.`,
        config: {
          responseMimeType: "application/json",
          responseSchema: {
            type: Type.OBJECT,
            properties: {
              title: { type: Type.STRING, description: "Action title" },
              description: { type: Type.STRING, description: "Detailed description of routine" },
              keyframes: {
                type: Type.ARRAY,
                items: {
                  type: Type.OBJECT,
                  properties: {
                    name: { type: Type.STRING },
                    durationMs: { type: Type.NUMBER },
                    delayAfterMs: { type: Type.NUMBER },
                    joints: {
                      type: Type.OBJECT,
                      properties: {
                        base: { type: Type.NUMBER },
                        shoulder: { type: Type.NUMBER },
                        elbow: { type: Type.NUMBER },
                        wristPitch: { type: Type.NUMBER },
                        wristRoll: { type: Type.NUMBER },
                        gripper: { type: Type.NUMBER }
                      },
                      required: ["base", "shoulder", "elbow", "wristPitch", "wristRoll", "gripper"]
                    },
                    comment: { type: Type.STRING }
                  },
                  required: ["name", "durationMs", "delayAfterMs", "joints"]
                }
              }
            },
            required: ["title", "description", "keyframes"]
          }
        }
      });

      const responseText = response.text || "{}";
      const sequenceData = JSON.parse(responseText);
      res.json(sequenceData);
    } catch (err: any) {
      console.error("Gemini Trajectory Generation Error:", err);
      res.status(500).json({ error: err.message || "Failed to generate sequence with AI" });
    }
  });

  // Mount Vite middleware for dev or static files for prod
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`[SO-ARM100] Server running on port ${PORT}`);
  });
}

startServer();
