---
title: "The Real Work Is the Plumbing: Notes on Mercor's 397B RL Recipe"
date: 2026-10-07
draft: false
tags: ["AI", "Reinforcement Learning", "LLM Agents", "Post-Training", "Infrastructure", "SkyRL"]
description: "A walk through Mercor and SkyRL's open recipe for RL post-training knowledge-work agents at 35B and 397B — and why the unglamorous de-risking work, not the hero run, is where the gains actually come from."
---

## Introduction

Mercor and the Berkeley SkyRL team just published a [step-by-step guide to RL post-training knowledge-work agents](https://www.mercor.com/blog/training-frontier-knowledge-work-agents-a-397b-rl-training-guide-with-skyrl/), and released the full training script, model weights, and eval traces. They took two open mixture-of-experts models — Qwen3.6-35B-A3B and Qwen3.5-397B-A17B — and post-trained them with pure reinforcement learning (no SFT warmup) to compete with Opus 4.5 on **APEX-Agents**, a benchmark of 480 realistic professional-services tasks across management consulting, investment banking, and corporate law. The 397B run improved Pass@1 by 70% relative, from 16.11% to 27.29%.

What makes the post worth reading isn't the headline number. It's that most of the document is about the work *before* the expensive training run — the environment infrastructure, the harness bugs, the token accounting, the systems tuning. That framing lines up almost exactly with what I keep running into building agent pipelines and batch-generation jobs: **the modeling is rarely the bottleneck; the plumbing is.**

This post walks their six-step recipe, flags the parts I think matter most, and ends with a few things I'd read skeptically.

## The setup: RL on worlds, not prompts

APEX-Agents is not a prompt-and-grade benchmark. Each task lives in a simulated company — dozens of PDFs, spreadsheets, slide decks, plus chat and email servers — and many tasks share a world. The agent operates through MCP tools or code execution, and a verifier scores the result. This is the long-horizon, cross-application shape that makes knowledge-work RL expensive: realistic environments are costly to build, and rollouts can run to 128k tokens.

Two deliberate choices frame the study. They skip SFT warmup because RL is the part of post-training that's hardest to get right, and they use SkyRL for its async training loop, easy harness integration, and swappable compute backends. The dataset is 1,928 expert-created tasks with the same shape as the public benchmark but no overlap — no contamination.

## Step 1: Environment, harness, and token accounting

This is the step the post spends the most on, and the one that resonated most with me. The claim that stuck: harness fixes alone — with **zero training** — moved the base 35B model from 22.74% to 28.69% mean reward. That's roughly what one epoch of training would have bought, bought instead by reading traces and fixing bugs.

The infrastructure lessons are the kind you only learn by getting burned:

- **Put a timeout on everything.** Anything without one eventually hangs a rollout for its entire end-to-end budget.
- **Isolate MCP clients per process.** Sharing one Python process across hundreds of agent loops caused constant MCP disconnects. They run each agent loop as its own Ray task.
- **Bypass judge rate limits.** An eval pass is modest traffic; RL at 800+ concurrent rollouts hits limits hard. Round-robin keys, retry with backoff.
- **Classify every error** as fail-the-trial vs. retry, rather than leaning on "mask errors during RL."

I've hit the mild version of all of these. Headless batch jobs that crash the machine at high parallelism and have to be capped to a handful of workers; flaky environments where you can't tell model failure from harness failure until you read the traces; the slow realization that "just mask the errors" is a way of training your model on your own bugs. Their suggestion — run an eval pass over the full training set at production concurrency and drive the non-model error rate to near zero *before* training — is the right instinct. You cannot debug a reward signal that's half noise.

The harness-optimization half is the same story one level up. They read traces, found the PowerPoint MCP tool returned `None` on success, found the PDF reader flattened multi-column tables into garbled text, found missing Python packages that made agents waste turns rediscovering their own sandbox. None of this shows up in a metric; it shows up in a trace. Their tip — point a coding agent at the traces to find per-tool failure patterns — is a nice loop: use agents to debug the environment you're training agents in.

### Token-in-token-out: the subtle one

The piece I'd foreground for anyone doing agentic RL is **token-in-token-out (TITO)**. The problem is easy to miss and silently corrupts training.

When you convert the inference engine's output into the trainer's input, you must not re-tokenize the engine's *text*. Say the vocabulary is `0: <`, `1: search`, `2: <search`, `3: >`. The engine generates the token sequence `0, 1, 3`. If you hand the trainer the string `<search>` without carrying the token IDs, the trainer may re-tokenize it to `2, 3`. Now the trainer is computing gradients on a token sequence the model never actually produced. In multi-turn settings there's a second misalignment: the output token IDs of turn N don't line up with the input token IDs of turn N+1.

Either way, your "on-policy" RL is quietly off-policy. The fix is to carry raw token IDs end to end — Mercor rewrote the harness to use `/completions` instead of string-in-string-out `/chat/completions`. It's unglamorous bookkeeping, and it's exactly the kind of thing that, left unfixed, makes a run mysteriously underperform with no error anywhere to point at.

## Step 2: RL systems tuning

With the environment stable, they tune the stack — vLLM for inference, Megatron for training, fully-async with in-flight weight updates to minimize stragglers. The three knobs worth remembering:

1. **Split the cluster so the trainer never waits.** Fix training GPUs, then add rollout GPUs until `wait_for_generation_buffer` hits zero. Their ratios were 12:4 (35B) and 12:8 (397B).
2. **Set rollout concurrency to the lower of two ceilings** — the systems ceiling (KV-cache capacity ÷ average trajectory length) and the algorithmic ceiling (staleness tolerance, `(max_staleness + 1) × mini_batch × n_samples`). For long-horizon tasks the KV-cache ceiling binds; they ran 550 (35B) and 300 (397B), well under the 1024 staleness ceiling.
3. **Check train–inference logprob mismatch.** A few steps in, compare logprobs between trainer and engine. This is how they caught a correctness bug in the combination of vLLM CPU offloading, GDN models, and in-flight weight sync. Below ~0.03 mean difference is healthy.

That last one is a good habit regardless of scale: a cheap diagnostic that catches an entire class of silent correctness bugs.

## Step 3: The overfitting run

Before the hero run, prove the tasks are learnable. They take a 32-task subset with non-zero reward variance, batch size 32, 8 samples per prompt, trained synchronously so each step is one epoch. If you can't overfit a handful of tasks, a full run has no chance.

The nice detail: when overfitting failed, it pointed back at Step 1. Tasks graded by diffing files before/after the rollout were much harder to overfit than tasks graded on the final response. The culprit was grading fidelity — switching to a third-party file-diffing tool made extraction reliable and the tasks became learnable. The de-risking steps aren't a checklist you pass once; a failure downstream sends you back upstream.

## Step 4: Algorithm ablations on the 35B

Only now do they spend real compute, and only on the smaller model. They ablate a few knobs they had concrete hypotheses about, evaluating each arm's epoch-1 checkpoint over 3 passes of the 480 held-out tasks:

- **Token aggregation (+3.9 pts).** `token_mean` lets the longest trajectories (2k–128k tokens) dominate the gradient. Switching to `prompt_mean` (aggregate equally per rollout group, as in DAPO) removes that bias and was the single biggest win.
- **Policy loss (DPPO vs. GLM-5 loss).** Within noise of each other on score, but DPPO changed *behavior* — more, shorter turns (21 → 32 turns; 834 → 588 tokens per turn).
- **Context nudge (+3.0 pts).** Inject a "wrap up" notice when 20% of context budget remains. Fewer rollouts blow their context, so fewer get zeroed, so more usable signal per batch. It's a training-time effect — all evals ran without it.
- **What didn't help:** overlong filtering cost 1.5 points; adaptive length penalty was neutral-to-negative.

Two honesty habits worth stealing: single-pass evals over 480 tasks are noisy (±1–3 points), so every number is a 3-pass mean and differences under ~1 point are ties; and they looked at *behavior*, not just reward — many turns, few tokens per turn, high tool-call success correlated with the best scores.

## Step 5: The 397B hero run

The payoff is almost anticlimactic, by design. They pick the configuration they're most confident in (DPPO + `prompt_mean` + the context nudge) and launch. Their stated takeaway: the only real difference between a 35B run and a 397B run is the systems work, which Step 2 already de-risked. The initial dip in Pass@1 is just async RL dynamics — easier tasks finish first.

## Step 6: Does it generalize, or is it welded to the harness?

This is the most interesting scientific question in the post. Recent work suggests RL gains are bound to the harness they were trained in. To test it, they swapped the MCP-based harness (Archipelago) for code-based OpenCode — no MCP servers at all, just `bash`, `read`, `grep`, `write`, `edit` — and re-evaluated.

The gains largely transferred, but **the 35B transferred noticeably better than the 397B.** The reason is revealing: over training, the 35B learned to lean on code execution rather than MCP tools, while the 397B stayed with MCP. A model that learned a *portable* skill (write code) generalizes; one that learned a *harness-specific* skill (call these MCP tools) is more welded to its scaffold. They confirmed the same pattern transferring to Terminal-Bench 2.1 with a different harness entirely. Meanwhile HLE and GPQA were flat — no regression, but no gain either.

The takeaway for anyone fine-tuning agents: what your model learns to *rely on* during training determines how much of the gain you keep when you move it. That's a design lever, not an accident.

## What I'd read skeptically

The engineering is genuinely useful and the open release is real. A few caveats keep this honest:

- **"Beats Opus 4.5" is on their own benchmark.** APEX-Agents is Mercor's, and the OTS training data shares its shape (if not its worlds). Strong signal in-distribution; not a general-capability claim.
- **The capability bump is narrow.** HLE and GPQA showed no regression *and* no improvement. The models got better at APEX-style agentic tasks, not smarter in general — which is exactly what targeted post-training should do, but worth stating plainly.
- **"Data > algorithms" is a convenient conclusion for a company that sells data.** It also happens to match what I see in practice — data and prompt quality routinely outweigh model-swapping — so I buy it. But the comparison is one algorithm knob (+3.9 pts) against the whole intervention (+10–12 pts), which isn't quite apples-to-apples.
- **Open script ≠ reproducible.** Releasing the full recipe is admirable, but a 397B async RL run is out of reach for almost everyone who'll read it. The genuinely reusable artifact here is the *checklist* — Steps 1–3 — not the hero run.

## Key Takeaways

1. **The plumbing is the work.** Harness fixes bought a full epoch's worth of gain with zero training. De-risk the environment before you spend compute.
2. **Carry your token IDs end to end.** TITO is subtle, silent, and will quietly make your on-policy RL off-policy if you re-tokenize engine output.
3. **Prove learnability before the hero run.** Overfit 32 tasks first; a failure there sends you back to Step 1, usually to the grader.
4. **Portable skills transfer; harness-specific ones don't.** The 35B generalized better because it learned to write code rather than call specific tools. What a model learns to rely on is a design choice.
5. **Read vendor benchmarks for what they are.** In-distribution wins on a proprietary benchmark are real but narrow; the transferable value is the methodology.

The honest summary of the post is its own: algorithm choices moved the models +3.9 points at best, while post-training as a whole moved them 10–12. The cleverness mattered less than the data and the infrastructure around it. That's not a glamorous conclusion, but it's the one that matches the work.
