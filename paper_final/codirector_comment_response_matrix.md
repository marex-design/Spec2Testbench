# Codirector Comment Response Matrix

| comment_id | codirector_comment | affected_sections | current_problem | required_action | files_to_modify | evidence_required | audit_finding | recommended_priority | completion_status |
|---|---|---|---|---|---|---|---|---|---|
| CD01 | Too many bullet points | all | manuscript is short prose and no review source exists | obtain reviewed draft and revise style | main.tex | codirector annotated copy | expert input required | MINOR | REQUIRES_EXPERT_INPUT |
| CD02 | Too many subsections | structure | current manuscript has few sections, source unavailable | compare against reviewed version | main.tex | annotated manuscript | blocked | MINOR | BLOCKED |
| CD03 | Fewer than 31 references | related work | references.bib is empty | audit verified bibliography | references.bib | verified sources | evidence available that bibliography is incomplete | MAJOR | EVIDENCE_AVAILABLE |
| CD04 | Claims lack evidence | results | 7+7 claim conflicts with V3 | link every claim to final files | main.tex,evidence_map.csv | final CSV/JSON | partially evidenced | CRITICAL | PARTIALLY_EVIDENCED |
| CD05 | Acronyms undefined | all | SPICE, WRDATA, PVT, LLM and EDA need first-use definitions | define at first occurrence | main.tex | acronym inventory | evidence available | MINOR | EVIDENCE_AVAILABLE |
| CD06 | Rewrite abstract | abstract | current abstract contains stale 7+7 and future-study wording | rewrite from final evidence | main.tex | V3 and expanded results | partially evidenced | MAJOR | PARTIALLY_EVIDENCED |
| CD07 | Use full Christian-Marie name | authors | exact requested name not found; repository has Christian Moanda Ndeko | confirm author identity | main.tex | signed author confirmation | expert input required | CRITICAL | REQUIRES_EXPERT_INPUT |
| CD08 | Missing figures | figures | no figure assets or environments | create evidence-driven figures | paper_final/figures | final CSVs and design approval | blocked by missing figures | MAJOR | NOT_STARTED |
| CD09 | Figure 1 invisible | figures | no Figure 1 exists | inspect reviewed PDF and recreate | main.tex,figures | reviewed PDF | blocked | MAJOR | BLOCKED |
| CD10 | Commands exceed margins | typesetting | current article has no command listings | inspect venue layout after rewrite | main.tex | compiled venue PDF | not yet testable | MINOR | NOT_STARTED |
| CD11 | Global architecture absent | architecture | current architecture section is prose only | add architecture figure | main.tex,figures | architecture source | partially evidenced | MAJOR | PARTIALLY_EVIDENCED |
| CD12 | LLM lacks usable results | LLM | no quantitative LLM evidence | remove primary LLM claims | main.tex | LLM campaign or explicit omission | evidence supports omission | CRITICAL | PARTIALLY_EVIDENCED |
| CD13 | Circuits too simple | threats | benchmark uses academic Level-1 models | discuss scope and limitation | main.tex | benchmark characterization | evidence available | MAJOR | PARTIALLY_EVIDENCED |
| CD14 | Human validation absent | validation | no signed inter-rater study located | obtain signed review or remove claim | reports,paper_final | signed review | blocked | MAJOR | BLOCKED |
| CD15 | Related Work too binary | related work | bibliography and comparison table absent | add nuanced sourced comparison | main.tex,references.bib | verified sources | not started | MAJOR | NOT_STARTED |
| CD16 | Differentiation from AnalogTester insufficient | related work | comparison exists only in legacy docs | write sourced non-hierarchical comparison | main.tex,references.bib | verified AnalogTester source | not started | MAJOR | NOT_STARTED |

The statuses intentionally do not use `RESOLVED` or `COMPLETED` during this read-only audit.
