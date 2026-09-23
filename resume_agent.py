import os
import json
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

class JobDescriptionAnalysis(BaseModel):
    target_role: str = Field(description="Normalized target title")
    seniority_level: str = Field(description="Seniority level")
    hard_skills: List[str] = Field(description="Core tools, platforms, and methodologies")
    core_competencies: List[str] = Field(description="Functional skills and competencies")
    key_metrics_expected: List[str] = Field(description="Target KPIs mentioned or implied")

class CandidateExperienceItem(BaseModel):
    company: str
    role: str
    dates: str
    raw_achievements: List[str]
    tools_mentioned: List[str]

class CandidateProfile(BaseModel):
    full_name: str
    email: Optional[str] = "candidate@example.com"
    phone: Optional[str] = "(555) 000-0000"
    location: Optional[str] = "Location, State"
    linkedin_or_site: Optional[str] = "linkedin.com/in/profile"
    all_tools: List[str] = Field(description="List of tools candidate verified having")
    experiences: List[CandidateExperienceItem]
    education_certs: List[str]

class SkillGapReport(BaseModel):
    direct_keyword_matches: List[str]
    adjacent_skills: List[str]
    missing_critical_skills: List[str]

class OptimizedRole(BaseModel):
    company: str
    role_title: str
    dates: str
    bullets: List[str]

class OptimizedResume(BaseModel):
    full_name: str
    contact_info: str
    professional_summary: str
    core_competencies: List[str]
    technical_stack: List[str]
    experience: List[OptimizedRole]
    education: List[str]

class AuditReport(BaseModel):
    passed: bool
    hallucination_detected: bool
    ats_score_out_of_100: int
    feedback: str

class ResumeAgentPipeline:
    def __init__(self, api_key: Optional[str] = None):
        self.client = genai.Client(api_key=api_key or os.getenv("GEMINI_API_KEY"))
        self.fast_model = "gemini-3.6-flash"
        self.reasoning_model = "gemini-3.6-flash"

    def _call_structured_llm(self, model: str, system_prompt: str, user_prompt: str, response_schema):
        response = self.client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.1,
            )
        )
        return response_schema.model_validate_json(response.text)

    def parse_job_description(self, raw_jd: str) -> JobDescriptionAnalysis:
        return self._call_structured_llm(
            self.fast_model,
            "You are an ATS parsing specialist. Strip corporate boilerplate. Extract exact skills, tools, and implied KPIs.",
            f"RAW JOB DESCRIPTION:\n{raw_jd}",
            JobDescriptionAnalysis
        )

    def parse_candidate_profile(self, raw_resume: str) -> CandidateProfile:
        return self._call_structured_llm(
            self.fast_model,
            "Extract every factual entity from the candidate background. nstated tools.",
            f"RAW CANDIDATE HISTORY:\n{raw_resume}",
            CandidateProfile
        )

    def analyze_skill_gap(self, jd: JobDescriptionAnalysis, profile: CandidateProfile) -> SkillGapReport:
        user_prompt = f"TARGET JD HARD SKILLS: {jd.hard_skills}\nTARGET JD CORE COMPETENCIES: {jd.core_competencies}\nCANDIDATE TOOLS INVENTORY: {profile.all_tools}"
        return self._call_structured_llm(
            self.fast_model,
            "Identify exact matches, adjacent functional equivalents, and critical missing skills.",
            user_prompt,
            SkillGapReport
        )

    def synthesize_resume(self, jd: JobDescriptionAnalysis, profile: CandidateProfile, gaps: SkillGapReport, feedback: Optional[str] = None) -> OptimizedResume:
        system_instruction = (
            "You are an executive resume architect. NEVER invent employers or tools in 'missing_critical_skills'. "
            "Write bullets using: Accomplished [X], as measured by [Y], by doing [Z]. "
            "Use placeholders like {{ESTIMATE: % efficiency}} if exact numbers are missing."
        )
        user_prompt = f"TARGET ROLE: {jd.target_role} ({jd.seniority_level})\nMATCHED KEYWORDS: {gaps.direct_keyword_matches}\nCANDIDATE DATA: {profile.model_dump_json()}\nAUDITOR FEEDBACK: {feedback or 'None'}"
        return self._call_structured_llm(
            self.reasoning_model,
            system_instruction,
            user_prompt,
            OptimizedResume
        )

    def audit_resume(self, resume: OptimizedResume, jd: JobDescriptionAnalysis, profile: CandidateProfile) -> AuditReport:
        user_prompt = f"TARGET JD SKILLS: {jd.hard_skills}\nCANDIDATE TOOLS: {profile.all_tools}\nSYNTHESIZED RESUME: {resume.model_dump_json()}"
        return self._call_structured_llm(
            self.fast_model,
            "Check for hallucinations and verify strong ATS keyword inclusion. Return passed=True only if zero hallucinations.",
            user_prompt,
            AuditReport
        )

    def run(self, raw_resume: str, raw_jd: str, max_retries: int = 1) -> OptimizedResume:
        jd_data = self.parse_job_description(raw_jd)
        profile_data = self.parse_candidate_profile(raw_resume)
        gap_analysis = self.analyze_skill_gap(jd_data, profile_data)
        
        feedback = None
        for attempt in range(max_retries + 1):
            resume = self.synthesize_resume(jd_data, profile_data, gap_analysis, feedback)
            audit = self.audit_resume(resume, jd_data, profile_data)
            if audit.passed or attempt == max_retries:
                return resume
            feedback = f"Revision needed: {audit.feedback}"
          
