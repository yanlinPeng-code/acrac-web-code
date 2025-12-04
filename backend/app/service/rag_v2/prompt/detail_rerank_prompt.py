from typing import List, Dict, Any

from app.schema.IntelligentRecommendation_schemas import PatientInfo, ClinicalContext
from app.service.rag_v2.prompt.base_prompt import BasePrompt


class DetailRerankPrompt(BasePrompt):


    def build_comprehensive_prompt_with_grading(
            self,
            all_scenarios: List[Dict[str, Any]],
            patient_info: PatientInfo,
            clinical_context: ClinicalContext,
            max_scenarios: int,
            max_recommendations_per_scenario: int,
            direct_return: bool,
    ) -> str:


         patient_info_content=self.build_patient_context(patient_info)
         clinical_context_content=self.build_clinical_context(clinical_context)
         scenarios_content=self.build_scenarios_with_recommend(all_scenarios)
         task_instruction=self.build_task_instruction(
             max_scenarios=max_scenarios,
             max_recommendations_per_scenario=max_recommendations_per_scenario,direct_return=False)


         return patient_info_content + "\n" + clinical_context_content + "\n" +scenarios_content+"\n"+ task_instruction
