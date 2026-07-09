from __future__ import annotations

from dataclasses import dataclass


DEFAULT_GENERATION_STYLE = "Create a post about a topic"


@dataclass(frozen=True, slots=True)
class PostGenerationStyle:
    label: str
    instructions: str
    example: str


POST_GENERATION_STYLES: dict[str, PostGenerationStyle] = {
    "Create posts from scratch": PostGenerationStyle(
        label="Create posts from scratch",
        instructions=(
            "Create an original LinkedIn post from the topic. Use a strong hook, a useful "
            "insight, and a natural closing question. Keep it practical and ready to post."
        ),
        example=(
            "I used to wait for perfect ideas before posting.\n\n"
            "That kept me silent.\n\n"
            "Now I start with one real problem, one lesson, and one question for the reader."
        ),
    ),
    "Create a post about a topic": PostGenerationStyle(
        label="Create a post about a topic",
        instructions=(
            "Create a clear LinkedIn post about the topic. Structure it as a hook, short "
            "context, core insight or lesson, then a CTA or reflective question."
        ),
        example=(
            "I used to think networking meant collecting business cards.\n\n"
            "Then I learned people remember the person who cared about their problem for 90 seconds."
        ),
    ),
    "Create a controversial post about a topic": PostGenerationStyle(
        label="Create a controversial post about a topic",
        instructions=(
            "Create a defensible contrarian LinkedIn post. Challenge common wisdom without "
            "being offensive. Include reasoning, acknowledge the counterpoint, then invite debate."
        ),
        example=(
            "Unpopular opinion: culture fit interviews often reward sameness.\n\n"
            "Values matter. But teams also need people who notice the blind spots everyone else missed."
        ),
    ),
    "Create a top mistakes post about a topic": PostGenerationStyle(
        label="Create a top mistakes post about a topic",
        instructions=(
            "Create a top mistakes post. Open by naming the repeated mistakes, list 3 to 5 "
            "mistakes with a short fix for each, then close with a useful takeaway."
        ),
        example=(
            "I keep seeing the same 5 resume mistakes:\n\n"
            "1. Listing responsibilities instead of results\n"
            "2. Using a generic summary\n"
            "3. Hiding the strongest project"
        ),
    ),
    "Create a daily routine post about a topic": PostGenerationStyle(
        label="Create a daily routine post about a topic",
        instructions=(
            "Create a daily routine post that feels specific, not generic. Use a sequential "
            "or timestamped breakdown, explain one non-obvious choice, then ask the reader about their routine."
        ),
        example=(
            "My mornings got calmer when I stopped opening messages first.\n\n"
            "6:00 - plan the top 3 priorities\n"
            "6:15 - movement\n"
            "6:45 - hardest task before the day gets noisy"
        ),
    ),
    "Create a how to start post about a topic": PostGenerationStyle(
        label="Create a how to start post about a topic",
        instructions=(
            "Create a beginner-friendly how-to-start post. Name the barrier, reassure the "
            "reader, give 3 to 5 concrete first steps, then close with a question."
        ),
        example=(
            "You do not need a perfect strategy to start.\n\n"
            "Step 1: Pick one problem you solved this week.\n"
            "Step 2: Explain it like you are helping one person.\n"
            "Step 3: Post the useful part."
        ),
    ),
    "Create a motivational post about a topic": PostGenerationStyle(
        label="Create a motivational post about a topic",
        instructions=(
            "Create a grounded motivational post. Tie encouragement to a concrete situation, "
            "avoid generic quotes, and make the lesson feel earned."
        ),
        example=(
            "One lost client is data, not a verdict.\n\n"
            "That shift helped me stop spiraling and start sending better outreach."
        ),
    ),
    "Create a skills to become successful post about a topic": PostGenerationStyle(
        label="Create a skills to become successful post about a topic",
        instructions=(
            "Create a skills-you-need post. Contrast what people assume success requires "
            "with the practical skills that actually matter. List 3 to 5 skills with one reason each."
        ),
        example=(
            "Nobody tells you these are the real skills behind a successful launch:\n\n"
            "1. Saying no to good ideas\n"
            "2. Writing one-pagers clearly\n"
            "3. Reading support tickets before dashboards"
        ),
    ),
    "Create a do's and don'ts post about a topic": PostGenerationStyle(
        label="Create a do's and don'ts post about a topic",
        instructions=(
            "Create a do's and don'ts post. Mirror the don'ts with better do's, keep each "
            "point short, and close with a practical takeaway."
        ),
        example=(
            "Cold outreach, done wrong vs. done right:\n\n"
            "Don't: pitch in the first message.\n"
            "Do: ask a specific question about something they recently shared."
        ),
    ),
}


def generation_style_labels() -> list[str]:
    return list(POST_GENERATION_STYLES)


def normalize_generation_style(label: str | None) -> PostGenerationStyle:
    cleaned = (label or "").strip()
    if not cleaned:
        return POST_GENERATION_STYLES[DEFAULT_GENERATION_STYLE]

    if cleaned in POST_GENERATION_STYLES:
        return POST_GENERATION_STYLES[cleaned]

    lowered = cleaned.lower().replace('"', "")
    aliases = {
        "create a top mistakes post about a topic": "Create a top mistakes post about a topic",
        "create a daily routine post about a topic": "Create a daily routine post about a topic",
        "create a how to start post about a topic": "Create a how to start post about a topic",
        "create a skills to become successful post about a topic": "Create a skills to become successful post about a topic",
        "create a dos and donts post about a topic": "Create a do's and don'ts post about a topic",
        "create a do's and don'ts post about a topic": "Create a do's and don'ts post about a topic",
    }
    return POST_GENERATION_STYLES[aliases.get(lowered, DEFAULT_GENERATION_STYLE)]


def generation_style_prompt(label: str | None) -> str:
    style = normalize_generation_style(label)
    return (
        f"Selected post creation style: {style.label}\n\n"
        f"Instructions:\n{style.instructions}\n\n"
        f"Style example:\n{style.example}"
    )
