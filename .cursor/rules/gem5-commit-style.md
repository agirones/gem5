# AI Agent Instruction: Writing Git Commit Messages for gem5

You are an expert AI software engineer. Whenever a commit message is required, your task is to analyze the changes currently staged in the Git staging area (`git diff --cached`) and write a commit message that complies strictly with the **gem5 Project Architecture Commit Conventions**.

---

## 1. Context and Source Material
- **Staging Area:** Always base your commit message on the output of `git diff --cached`. Do not include unstaged changes.
- **Component Tags:** You must cross-reference the modified file paths with the `MAINTAINERS.yaml` file located in the root of the repository to determine the correct tags to use.

---

## 2. Commit Message Structure and Formatting Rules

Your generated commit message must follow this exact template:

```text
<tags>: <Short, imperative-style summary sentence>

<Detailed description paragraph explaining the WHY and WHAT of the change.
Wrap lines to ensure no line exceeds 72 characters.>

GitHub Issue: <URL to the relevant GitHub issue if applicable. It should explicity stated in the prompt>

---

## 3. Prohibited Content

- **Never add `Co-authored-by` trailers** (including `Co-authored-by: Cursor <cursoragent@cursor.com>` or any other co-author line). Commit messages must contain only the subject, body, and an optional GitHub Issue line as described above.