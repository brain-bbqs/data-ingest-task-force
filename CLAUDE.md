# Agent instructions

## Pull requests

Every pull request you open must record the prompt that led to it, so the PR
explains not just what changed but what was actually asked for. Reviewers can
then tell a faithful implementation from a drifting one, and a later reader can
reconstruct the intent without hunting down the original session.

End the PR description with the originating prompt, verbatim, inside a
collapsed `<details>` block:

```markdown
<details>
<summary>Original prompt</summary>

> ...the user's prompt, quoted exactly as it was given...

</details>
```

Rules:

- **Verbatim.** Quote the prompt as it was written — do not summarize, correct
  typos, reword, or tidy it up. If it spanned several messages, include each of
  them in order.
- **Collapsed.** Keep it inside `<details>` so it never crowds out the summary
  of the change itself.
- **Last.** It goes at the end of the description, after the actual write-up.
- **Every PR**, including small follow-ups. If a PR grew out of follow-up
  instructions, append those to the same block rather than dropping them.
- **Redact secrets.** If a prompt contains a credential, token, or private URL,
  replace just that value with `[redacted]` and leave the rest untouched.
