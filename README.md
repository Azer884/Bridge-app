# Gesir.AI

> A whatsapp-AI extension to answer customer's inquiry for a service provided by an SME.

---

## Team Information

| Field                  | Details                                     |
| ---------------------- | ------------------------------------------- |
| **Team Name**          |  HRISSA                                     |
| **Team Domain**        |  Domain 2                                   |
| **Main SDG**           |SDG 8 - Descent work and economic growth     |
|   **Sub SDG**          |SDG 9 - Industry, Innovation and Infrastructure|
| **Team Leader**        | Azer Hamdaoui                               |
| **University**         |Xiamen University Malaysia                   |
| **Number of Members**  | 5                                           |

## Links

| Resource          | Link                                           |
| ----------------- | ---------------------------------------------- |
| GitHub Repository | (https://github.com/Azer884/Bridge-app)        |
| Replit Project    | https://replit.com/@your-username/your-project |
| Live Demo         | https://your-project.replit.app                |
| RunPod Endpoint   | https://api.runpod.ai/v2/ose8agxpb9p1mr/runsync|
| Slide Deck        | https://example.com/slides                     |
| Demo Video        | https://example.com/demo-video                 |

---

## Overview

### Problem
Many SMEs and startups lose valuable time to constant back-and-forth communication with clients to clarify requests, answer inquiries, and negotiate job details. This time-consuming process increases managers’ workloads, delays decision-making, and distracts them from essential business operations and customer satisfaction.

### Solution

Giser.AI uses AI to understand customer messages, voice notes, and images, automatically extracting key requirements and identifying missing information to minimize repetitive inquiries. It generates a complete job briefing with estimated costs, required materials, and available time slots, allowing managers to review and accept or decline jobs with a single click.
### Key Features

- **Feature 1** — AI-Powered Customer Request Analysis.
- **Feature 2** — Automated Job Briefing & Cost Estimation.
- **Feature 3** — Smart Scheduling & One-Click Decisions.

### Tech Stack

| Layer         | Technology                   |
| ------------- | ---------------------------- |
| Frontend      | e.g. HTML, React             |
| Backend       | e.g. Python, Flask / FastAPI |
| Database      | e.g. PostgreSQL, SQLite      |
| AI / Compute  | RunPod (GPU)                 |
| Hosting / Dev | Replit                       |

---

## Project Structure

```
.
├── docs/                    # Screenshots, diagrams
├── runpod/
│   └── handler.py           # RunPod serverless handler (GPU workload)
├── src/
│   ├── main.py              # Application entry point
│   └── utils.py             # Helper functions
├── submission/              # Required submission documents
│   ├── REPLIT PROOF OF USE.pdf
│   ├── RUNPOD PROOF OF USE.pdf
│   └── Submission Template SDC Hackathon.pdf
├── tests/
│   └── test_utils.py        # Unit tests
├── .env.example             # Example environment variables
├── .gitignore
├── .replit                  # Replit run configuration
├── LICENSE
├── requirements.txt         # Python dependencies
└── README.md
```

### Architecture

```
User ──► Replit (App / API) ──► RunPod Endpoint (GPU model)
                │
                └──► Response returned to user
```

---

## How to Run

### Option 1 — Run on Replit (Recommended)

1. Open the [Replit Project](https://replit.com/@your-username/your-project), or import this repository via **Create Repl → Import from GitHub**.
2. Open the **Secrets** tab (🔒) and add the variables listed in `.env.example`:
   - `RUNPOD_API_KEY`
   - `RUNPOD_ENDPOINT_ID`
3. Click **Run**. Replit uses the `.replit` file to start `python src/main.py`.

### Option 2 — Run Locally

```bash
# 1. Clone the repository
git clone https://github.com/your-username/your-project.git
cd your-project

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env            # then fill in your values

# 5. Run the app
python src/main.py
```

### Run Tests

```bash
python -m unittest discover tests
```

---

## How We Use Replit *(Required)*

Describe how your team used Replit. For example:

- **Development:** Collaborative coding in a shared Repl using Multiplayer.
- **Hosting:** The app is deployed with Replit Deployments at the Live Demo link above.
- **Secrets:** API keys are stored in Replit Secrets, never in the code.

📄 Proof of use: [`submission/REPLIT PROOF OF USE.pdf`](submission/REPLIT%20PROOF%20OF%20USE.pdf)

## How We Use RunPod *(Required)*

Describe how your team used RunPod. For example:

- **Workload:** Model inference (e.g. text generation, image processing) runs on a RunPod GPU.
- **Setup:** `runpod/handler.py` is deployed as a **RunPod Serverless Endpoint**.
- **Integration:** The Replit app sends requests to the endpoint using `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID`.

Example request:

```bash
curl -X POST https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"prompt": "Hello"}}'
```

📄 Proof of use: [`submission/RUNPOD PROOF OF USE.pdf`](submission/RUNPOD%20PROOF%20OF%20USE.pdf)

---

## Challenges & Learnings

- What challenges did you face, and how did you overcome them?
- what did your team learned

## Future Improvements

- [ ] Improvement 1
- [ ] Improvement 2

## Team

| Name              | Role                                       | GitHub                                   |
| -----------       | -------------------------------------------| ---------------------------------------- |
| Azer Hamdaoui     | Team Lead / Runpod/ AI Expe                | [@username](https://github.com/username) |
| Omar Bouhlel      | Frontend / AI-calendar Developer           | [@username](https://github.com/username) |
| Tarek ben slimen  | AI-whatsapp voice/call Messages Expert     | [@username](https://github.com/username) |
| Ilyess Hassine    | Whatsapp Linkage Analyzer                  | [@username](https://github.com/username) |
| Moetez Soltani    | Representater / Organizer                  |@Moe-MY                                   |

---

## Submission Checklist

- [ ] Team name, domain (Domain 1 / Domain 2) and SDG track filled in
- [ ] Slide deck link added
- [ ] Demo video link added
- [ ] Replit used, with proof of use in `submission/`
- [ ] RunPod used, with proof of use in `submission/`
- [ ] Submission template completed in `submission/`
- [ ] "How to Run" steps verified
- [ ] No API keys or secrets committed to the repository

## License

This project is licensed under the [Apache License 2.0](LICENSE).
