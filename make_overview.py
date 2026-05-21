from html import escape
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


OUT = Path("Parker_AI_Overview.docx")


C = {
    "orange": "D97757",
    "dark_blue": "1E3A5F",
    "mid_blue": "2E5D9F",
    "light_blue": "D5E8F0",
    "light_gray": "F5F5F5",
    "med_gray": "DDDDDD",
    "dark_gray": "444444",
    "white": "FFFFFF",
    "black": "111111",
}


def tag(name, attrs=None, body=""):
    attrs = attrs or {}
    attr_text = "".join(f' {k}="{escape(str(v), quote=True)}"' for k, v in attrs.items())
    return f"<{name}{attr_text}>{body}</{name}>"


def text_run(text, *, bold=False, italic=False, size=22, color=None):
    props = [tag("w:rFonts", {"w:ascii": "Arial", "w:hAnsi": "Arial"})]
    props.append(tag("w:sz", {"w:val": size}))
    if color:
        props.append(tag("w:color", {"w:val": color}))
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    return tag(
        "w:r",
        body=tag("w:rPr", body="".join(props))
        + tag("w:t", {"xml:space": "preserve"}, escape(text)),
    )


def paragraph(
    runs,
    *,
    align=None,
    before=60,
    after=120,
    style=None,
    border_bottom=False,
):
    if isinstance(runs, str):
        runs = [text_run(runs, color=C["black"])]
    props = []
    if style:
        props.append(tag("w:pStyle", {"w:val": style}))
    if align:
        props.append(tag("w:jc", {"w:val": align}))
    props.append(tag("w:spacing", {"w:before": before, "w:after": after}))
    if border_bottom:
        props.append(
            tag(
                "w:pBdr",
                body=tag(
                    "w:bottom",
                    {
                        "w:val": "single",
                        "w:sz": "4",
                        "w:space": "1",
                        "w:color": C["med_gray"],
                    },
                ),
            )
        )
    return tag("w:p", body=tag("w:pPr", body="".join(props)) + "".join(runs))


def heading(text, level=1):
    if level == 1:
        return paragraph(
            [text_run(text, bold=True, size=32, color=C["dark_blue"])],
            style="Heading1",
            before=400,
            after=160,
        )
    if level == 2:
        return paragraph(
            [text_run(text, bold=True, size=26, color=C["mid_blue"])],
            style="Heading2",
            before=280,
            after=100,
        )
    return paragraph(
        [text_run(text, bold=True, size=22, color=C["dark_gray"])],
        before=200,
        after=80,
    )


def bullet(text):
    return paragraph([text_run("- " + text, size=22, color=C["black"])], before=40, after=40)


def bullet_bold(label, rest):
    return paragraph(
        [
            text_run("- " + label, bold=True, size=22, color=C["black"]),
            text_run(rest, size=22, color=C["black"]),
        ],
        before=40,
        after=40,
    )


def spacer(points=120):
    return paragraph([text_run("")], before=points, after=0)


def divider():
    return paragraph([text_run("")], before=160, after=160, border_bottom=True)


def page_break():
    return tag("w:p", body=tag("w:r", body="<w:br w:type=\"page\"/>"))


def table_cell(content, *, width, fill=None, borders=True):
    border = (
        '<w:tcBorders>'
        '<w:top w:val="single" w:sz="1" w:color="DDDDDD"/>'
        '<w:left w:val="single" w:sz="1" w:color="DDDDDD"/>'
        '<w:bottom w:val="single" w:sz="1" w:color="DDDDDD"/>'
        '<w:right w:val="single" w:sz="1" w:color="DDDDDD"/>'
        '</w:tcBorders>'
        if borders
        else '<w:tcBorders><w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/><w:right w:val="nil"/></w:tcBorders>'
    )
    shading = tag("w:shd", {"w:fill": fill}) if fill else ""
    props = (
        tag("w:tcW", {"w:w": width, "w:type": "dxa"})
        + border
        + shading
        + '<w:tcMar><w:top w:w="100" w:type="dxa"/><w:left w:w="140" w:type="dxa"/><w:bottom w:w="100" w:type="dxa"/><w:right w:w="140" w:type="dxa"/></w:tcMar>'
    )
    return tag("w:tc", body=tag("w:tcPr", body=props) + "".join(content))


def table(rows, widths, header=False):
    body = []
    for row_index, row in enumerate(rows):
        cells = []
        fill = C["light_gray"] if row_index % 2 else C["white"]
        for col_index, value in enumerate(row):
            is_header = header and row_index == 0
            cell_fill = C["dark_blue"] if is_header else fill
            color = C["white"] if is_header else (C["dark_blue"] if col_index == 0 else C["dark_gray"])
            cells.append(
                table_cell(
                    [
                        paragraph(
                            [text_run(str(value), bold=is_header or col_index == 0, size=20, color=color)],
                            before=0,
                            after=0,
                        )
                    ],
                    width=widths[col_index],
                    fill=cell_fill,
                )
            )
        body.append(tag("w:tr", body="".join(cells)))
    return tag(
        "w:tbl",
        body=(
            tag("w:tblPr", body=tag("w:tblW", {"w:w": sum(widths), "w:type": "dxa"}))
            + tag("w:tblGrid", body="".join(tag("w:gridCol", {"w:w": w}) for w in widths))
            + "".join(body)
        ),
    )


def highlight_box(title, lines, fill=None):
    fill = fill or C["light_blue"]
    content = [
        paragraph([text_run(title, bold=True, size=22, color=C["dark_blue"])], before=20, after=80)
    ]
    content.extend(bullet(line) for line in lines)
    return table_cell([*content], width=9360, fill=fill, borders=False).join if False else tag(
        "w:tbl",
        body=tag("w:tblPr", body=tag("w:tblW", {"w:w": 9360, "w:type": "dxa"}))
        + tag("w:tblGrid", body=tag("w:gridCol", {"w:w": 9360}))
        + tag("w:tr", body=table_cell(content, width=9360, fill=fill, borders=False)),
    )


def document_xml():
    body = []

    body.append(paragraph([text_run("P.A.R.K.E.R", bold=True, size=72, color=C["orange"])], align="center", before=1200, after=120))
    body.append(paragraph([text_run("Personal AI with Recursive Knowledge & Episodic Recall", size=28, color=C["mid_blue"])], align="center", before=0, after=80))
    body.append(paragraph([text_run("A Complete Project Overview for Non-Technical Readers", italic=True, size=22, color=C["dark_gray"])], align="center", before=0, after=600))
    body.append(highlight_box("Core idea", [
        "Most AI assistants forget you when the window closes.",
        "Parker compounds every conversation into long-term private memory.",
    ], C["dark_blue"]))
    body.append(spacer(400))
    body.append(paragraph([text_run("Built by Pavan - IIT Guwahati", size=20, color=C["dark_gray"])], align="center"))
    body.append(page_break())

    body.append(heading("1. What Is Parker?"))
    body.append(paragraph("Parker is a personal AI assistant, similar in concept to JARVIS from the Iron Man films, built and owned entirely by its creator, Pavan. It runs on Pavan's own computer, stores data in Pavan's own database, and is designed to become more personalized with every conversation."))
    body.append(paragraph("The defining characteristic is memory. Parker does not treat each chat as isolated. Conversations, facts, projects, and decisions are stored and organized so Parker can return to old context days, weeks, or years later."))
    body.append(highlight_box("Parker in one sentence:", [
        "A fully private, always-remembering AI assistant that combines modern language models with the memory of a perfect digital journal."
    ]))

    body.append(heading("2. What Parker Can Do"))
    body.append(heading("Talk to You Like JARVIS", 2))
    body.append(paragraph("Parker's personality is modeled on JARVIS: calm, precise, dry-witted, and competent. The tone is enforced through prompt rules and response repair logic."))
    body.append(heading("Remember Everything, Forever", 2))
    body.append(paragraph("Parker stores memory in four layers:"))
    body.append(bullet_bold("Profile - ", "Stable identity facts, preferences, tools, university, hardware, and long-lived context."))
    body.append(bullet_bold("Facts - ", "Discrete memories tagged by importance, with critical facts always available."))
    body.append(bullet_bold("Projects - ", "Multi-session project tracking with status, stack, decisions, and open questions."))
    body.append(bullet_bold("Episodes - ", "Structured summaries of conversation turns that roll up into day, week, month, and year summaries."))
    body.append(heading("Search the Internet Instantly", 2))
    body.append(paragraph("Parker can use a self-hosted search system to retrieve current information from multiple sources when needed."))
    body.append(heading("Control Your Computer", 2))
    body.append(paragraph("Parker can interact with websites, desktop applications, forms, browser pages, and application windows on behalf of the user."))
    body.append(heading("Hear and Speak", 2))
    body.append(paragraph("Voice interaction is supported through local speech-to-text and local text-to-speech systems."))
    body.append(heading("Be Reached Anywhere via Telegram", 2))
    body.append(paragraph("A Telegram bot interface allows Parker to be used from another device while still enforcing access control."))

    body.append(divider())
    body.append(heading("3. How the Memory Works"))
    body.append(paragraph("Parker's memory architecture is the most technically sophisticated part of the project. Instead of saving raw chat logs forever, it distills conversations into structured summaries and searchable facts."))
    body.append(table([
        ["Layer", "What It Stores"],
        ["Profile", "Stable identity, preferences, tools, and key personal context."],
        ["Facts", "Discrete facts with importance levels and automatic archival."],
        ["Projects", "Project status, stack, decisions, history, and open threads."],
        ["Episodes", "Conversation summaries that roll up into day, week, month, and year memory."],
    ], [2200, 7160], header=True))
    body.append(heading("The Summary Tree", 2))
    body.append(bullet("Each conversation turn becomes a chat-level memory entry."))
    body.append(bullet("All turns in a day become a day summary."))
    body.append(bullet("Days roll into weeks, weeks into months, and months into years."))
    body.append(paragraph("For time-based questions such as what happened yesterday, Parker can jump directly to the relevant date. For meaning-based questions, it uses semantic search over embeddings."))

    body.append(divider())
    body.append(heading("4. Privacy and Data Ownership"))
    body.append(highlight_box("Everything is local and private:", [
        "Conversation memory is stored in PostgreSQL on Pavan's own computer.",
        "Memory search and embeddings run locally.",
        "Speech recognition runs locally.",
        "The main external dependency is language model inference through Groq.",
    ]))

    body.append(divider())
    body.append(heading("5. The Technology Stack"))
    body.append(table([
        ["Component", "Plain-English Role"],
        ["Groq + LLaMA", "The response-generating brain."],
        ["LangGraph", "The workflow manager for each turn."],
        ["PostgreSQL + pgvector", "The long-term memory database and semantic search layer."],
        ["Ollama", "Local embedding generation for memory retrieval."],
        ["Faster-Whisper + Silero VAD", "Local voice transcription and speech detection."],
        ["Chatterbox TTS", "Local voice synthesis and voice cloning."],
        ["SearXNG", "Self-hosted internet search."],
        ["Telegram Bot", "Remote access from phone or other devices."],
        ["Docker", "Runs supporting services reliably."],
    ], [2600, 6760], header=True))

    body.append(divider())
    body.append(heading("6. How a Conversation Turn Works"))
    body.append(highlight_box("Step 1 - Classify", ["Decide whether to retrieve memory and whether new information should be stored."], C["light_gray"]))
    body.append(highlight_box("Step 2 - Retrieve Memory", ["Assemble profile, critical facts, projects, and relevant episode summaries."], C["light_gray"]))
    body.append(highlight_box("Step 3 - Generate Response", ["Inject memory into the prompt and generate a Parker-style answer."], C["light_gray"]))
    body.append(highlight_box("Step 4 - Save Memories", ["Save profile updates, facts, projects, and episode summaries in background jobs."], C["light_gray"]))

    body.append(divider())
    body.append(heading("7. How to Access Parker"))
    body.append(table([
        ["Command", "Action"],
        ["Type a message", "Send a text message to Parker."],
        ["V + Enter", "Switch to voice input mode."],
        ["T + Enter", "Switch back to text input mode."],
        ["/profile", "Display stored profile memory."],
        ["/facts", "List stored facts."],
        ["/projects", "List tracked projects."],
        ["exit / quit / bye", "Safely shut down Parker."],
    ], [2400, 6960], header=True))

    body.append(divider())
    body.append(heading("8. What Makes Parker Unique"))
    body.append(table([
        ["Feature", "Commercial AI", "Parker"],
        ["Memory", "Session-limited", "Permanent hierarchical memory"],
        ["Data ownership", "Vendor servers", "Local machine"],
        ["Personality", "Generic assistant", "Custom JARVIS-style character"],
        ["Internet access", "Product-dependent", "Self-hosted SearXNG"],
        ["Voice", "Often cloud processed", "Local speech and cloned voice"],
        ["Projects", "Limited", "Multi-session project state"],
    ], [2400, 3480, 3480], header=True))

    body.append(divider())
    body.append(heading("9. Setup Overview"))
    body.append(table([
        ["Component", "Purpose"],
        ["Python 3.11+", "Runs Parker."],
        ["Docker Desktop", "Runs database and search containers."],
        ["Ollama", "Runs local embeddings."],
        ["Groq API keys", "Power language model responses."],
        ["mpv", "Plays synthesized audio."],
        ["Chatterbox TTS", "Local voice synthesis."],
    ], [2400, 6960], header=True))

    body.append(divider())
    body.append(heading("10. Design Philosophy"))
    body.append(heading("1. Memory that scales", 3))
    body.append(paragraph("Raw transcripts are replaced by structured summaries and semantically searchable memory."))
    body.append(heading("2. Latency that never compounds", 3))
    body.append(paragraph("Memory extraction runs in background jobs so chat responses are not delayed."))
    body.append(heading("3. Personality that holds", 3))
    body.append(paragraph("The JARVIS character is enforced through prompt rules and post-generation repair."))

    body.append(divider())
    body.append(heading("11. Current Scope and Limitations"))
    body.append(bullet_bold("Single user: ", "Designed for Pavan, not multi-user deployment."))
    body.append(bullet_bold("Windows primary: ", "Desktop automation is Windows-oriented."))
    body.append(bullet_bold("Groq dependency: ", "Language responses use Groq API calls."))
    body.append(bullet_bold("Voice cloning setup: ", "Best experience requires NVIDIA GPU support."))
    body.append(bullet_bold("No mobile app: ", "Mobile access is through Telegram."))

    body.append(divider())
    body.append(heading("12. Summary"))
    body.append(paragraph("Parker is a production-grade personal AI system built around long-term memory, local ownership, voice interaction, internet access, and project continuity."))
    body.append(paragraph("It is not just a chatbot. It is a system designed to grow with its user."))
    body.append(highlight_box("Final thought", ["Parker is not a chatbot. It is a system that grows with you."], C["dark_blue"]))
    body.append(paragraph([text_run("Built by Pavan - IIT Guwahati - MIT License", size=18, color=C["dark_gray"])], align="center"))

    body.append(
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:w10="urn:schemas-microsoft-com:office:word" '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
        'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
        'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" '
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
        'mc:Ignorable="w14 wp14">'
        + tag("w:body", body="".join(body))
        + "</w:document>"
    )


def styles_xml():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:pPr><w:outlineLvl w:val="0"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:b/><w:color w:val="1E3A5F"/><w:sz w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:pPr><w:outlineLvl w:val="1"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:b/><w:color w:val="2E5D9F"/><w:sz w:val="26"/></w:rPr>
  </w:style>
</w:styles>"""


def write_docx():
    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        "word/_rels/document.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
        "word/styles.xml": styles_xml(),
        "word/document.xml": document_xml(),
    }

    with ZipFile(OUT, "w", ZIP_DEFLATED) as docx:
        for name, content in files.items():
            docx.writestr(name, content)


if __name__ == "__main__":
    write_docx()
    print(f"Done: {OUT.resolve()}")
