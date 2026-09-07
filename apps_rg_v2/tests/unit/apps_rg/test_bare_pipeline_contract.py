"""Focused contract tests for the one public Apps RG resume pipeline."""

from __future__ import annotations

from apps_rg.bare_pipeline import _validate_outreach_email, _validate_tailored_resume


def _complete_resume() -> str:
    return """# Ada Candidate
ada@example.com

## EXECUTIVE SUMMARY
Executive AI leader.

## CORE COMPETENCIES
- Partnerships
- Enterprise AI
- Cloud Architecture
- AI Governance
- Technical Leadership
- Platform Productization

## PROFESSIONAL EXPERIENCE
### Acme Corp — Remote
**VP Engineering** | 2020–Present
- Built a platform.

### Earlier Co — Remote
**Director** | 2017–2020
- Led delivery.

## EDUCATION
**MS, Computer Science** — Example University

## CERTIFICATIONS
- Example Certification
""" + ("\nEvidence-backed delivery." * 60)


def _target_resume(
    *,
    competency_count: int = 6,
    unify_bullet_count: int = 6,
    ibm_bullet_count: int = 5,
    include_technical_expertise: bool = False,
    include_embedded_outreach_email: bool = False,
) -> str:
    competencies = "\n".join(f"- Competency {index}" for index in range(competency_count))
    unify_bullets = "\n".join(f"- Unify outcome {index}" for index in range(unify_bullet_count))
    ibm_bullets = "\n".join(f"- IBM outcome {index}" for index in range(ibm_bullet_count))
    technical_expertise = "\n## TECHNICAL EXPERTISE\nDuplicated skills.\n" if include_technical_expertise else ""
    embedded_outreach = "\nSubject: Improperly embedded email\nHello Hiring Team,\n" if include_embedded_outreach_email else ""
    return f"""# Ada Candidate
ada@example.com

## EXECUTIVE SUMMARY
Executive AI leader with enterprise partnership delivery experience.

## CORE COMPETENCIES
{competencies}

## PROFESSIONAL EXPERIENCE
### Unify Consulting — Remote
**SVP Engineering** | 2020–Present
{unify_bullets}

### IBM — Remote
**Partner** | 2017–2020
{ibm_bullets}
{technical_expertise}
{embedded_outreach}
## EDUCATION
**MS, Computer Science** — Example University

## CERTIFICATIONS
- Example Certification
""" + ("\nEvidence-backed delivery." * 60)


def test_x1_requires_every_resume_section_and_source_employer() -> None:
    result = _validate_tailored_resume(
        _complete_resume(),
        required_employers=("Acme Corp", "Earlier Co"),
    )

    assert result["status"] == "PASS"
    assert result["missing"] == []
    assert result["checks"]["employers"] == {"Acme Corp": True, "Earlier Co": True}


def test_x1_rejects_a_resume_missing_a_required_section() -> None:
    incomplete = _complete_resume().replace("## CERTIFICATIONS\n- Example Certification\n", "")

    result = _validate_tailored_resume(incomplete, required_employers=("Acme Corp", "Earlier Co"))

    assert result["status"] == "FAIL"
    assert "heading:CERTIFICATIONS" in result["missing"]


def test_x1_enforces_canonical_competency_and_employment_bullet_shape() -> None:
    valid = _validate_tailored_resume(
        _target_resume(),
        required_employers=("Unify Consulting", "IBM"),
    )

    assert valid["status"] == "PASS"
    assert valid["shape"]["core_competency_category_count"] == {
        "actual": 6,
        "minimum": 6,
        "maximum": 8,
    }
    assert valid["shape"]["employment_bullet_counts"] == {
        "unify_bullet_count": {"actual": 6, "required": 6},
        "ibm_bullet_count": {"actual": 5, "required": 5},
    }

    invalid = _validate_tailored_resume(
        _target_resume(
            competency_count=9,
            unify_bullet_count=5,
            ibm_bullet_count=6,
            include_technical_expertise=True,
            include_embedded_outreach_email=True,
        ),
        required_employers=("Unify Consulting", "IBM"),
    )

    assert invalid["status"] == "FAIL"
    assert set(invalid["missing"]) >= {
        "core_competency_category_count",
        "unify_bullet_count",
        "ibm_bullet_count",
        "forbidden_heading:TECHNICAL EXPERTISE",
        "outreach_email_embedded_in_resume",
    }


def test_x1_requires_a_targeted_email_with_subject() -> None:
    result = _validate_outreach_email(
        """Subject: Applied AI Partnerships

Hello Anthropic Hiring Team,

I am writing about the Manager of Applied AI Architecture, Partnerships role at Anthropic.
""",
        company="Anthropic",
        role="Manager of Applied AI Architecture, Partnerships",
    )

    assert result["status"] == "PASS"
    assert result["missing"] == []
