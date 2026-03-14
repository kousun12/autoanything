# Prompt Optimization Example

This is a non-ML example challenge that uses the same AutoAnything structure as the root GPT training
challenge, but with a different mutable artifact: a prompt template.

Agents optimize `state/prompt.md`. The private evaluator would run the prompt against a hidden
classification set and score it by held-out accuracy.
