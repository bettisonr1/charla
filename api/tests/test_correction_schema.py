from app.schemas.correction import CorrectionReport, ErrorCategory


def test_correction_report_parses_model_output() -> None:
    report = CorrectionReport.model_validate(
        {
            "corrections": [
                {
                    "original": "Yo soy cansado",
                    "corrected": "Estoy cansado",
                    "category": "ser_estar",
                    "explanation": "Usamos 'estar' para estados temporales.",
                }
            ]
        }
    )
    assert report.corrections[0].category is ErrorCategory.SER_ESTAR
    assert report.natural_rewrite is None
