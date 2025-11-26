# 推荐系统评估接口文档

## 概述

本文档描述了推荐系统评估模块的接口规范，用于测试推荐系统的命中率和性能。

## 详情

### 现在我有以下api接口：

####  1.第一个接口的url是：http://203.83.233.236:5188/api/v1/acrac-code/simple-recommend

请求体python映射类：

```python
class IntelligentRecommendationRequest(BaseModel):
    """智能推荐请求模型"""
    patient_info: Optional[PatientInfo] = Field(..., description="患者基本信息")
    clinical_context: Optional[ClinicalContext] = Field(..., description="临床上下文信息")
    search_strategy: Optional[SearchStrategy] = Field(None, description="检索权重配置")
    retrieval_strategy: Optional[RetrievalRequest] = Field(None, description="检索的策略配置")
    direct_return:Optional[bool]=Field(True,description="是否直接返回json检索结果")
    standard_query:Optional[str]=Field("",description="标准问题，该问题主要用于测试")

class PatientInfo(BaseModel):
    """患者基本信息"""
    age: Optional[int] = Field(None, description="患者年龄", ge=0, le=150)
    gender: Optional[str] = Field(None, description="患者性别：男/女")
    pregnancy_status: Optional[str] = Field(None, description="妊娠状态：妊娠期/哺乳期/非妊娠期")
    allergies: Optional[List[str]] = Field(None, description="过敏史列表")
    comorbidities: Optional[List[str]] = Field(None, description="合并症列表")
    physical_examination: Optional[str] = Field(None, description="检查报告")


class ClinicalContext(BaseModel):
    """临床上下文信息"""
    department: Optional[str]= Field(..., description="科室名称", min_length=2, max_length=50)
    chief_complaint: Optional[str] = Field(..., description="主诉", min_length=2, max_length=500)
    medical_history: Optional[str] = Field(None, description="既往病史", max_length=2000)
    present_illness: Optional[str] = Field(None, description="现病史", max_length=2000)
    diagnosis: Optional[str] = Field(None, description="医生主诊断结果", max_length=500)
    symptom_duration: Optional[str] = Field(None, description="症状持续时间")
    symptom_severity: Optional[str] = Field(None, description="症状严重程度：轻度/中度/重度")


class SearchStrategy(BaseModel):
    """检索策略配置"""
    vector_weight: Optional[float] = Field(0.4, description="向量检索权重", ge=0, le=1)
    keyword_weight: Optional[float] = Field(0.3, description="关键词检索权重", ge=0, le=1)
    diversity_weight: Optional[float] = Field(0.3, description="多样性权重", ge=0, le=1)
class RetrievalRequest(BaseModel):
    enable_reranking: Optional[bool] = Field(True, description="是否启用llm重排序")
    need_llm_recommendations: Optional[bool] = Field(True, description="是否基于这些场景进行llm的推荐")
    apply_rule_filter: Optional[bool] = Field(True, description="是否应用规则过滤")
    top_scenarios: Optional[int] = Field(10, description="返回的场景数量", ge=1, le=50)
    top_recommendations_per_scenario: Optional[int] = Field(5, description="每个场景的推荐数量", ge=1, le=20)
    similarity_threshold: Optional[float] = Field(0.6, description="相似度阈值", ge=0.1, le=0.9)
    min_appropriateness_rating: Optional[int] = Field(None, description="最低适宜性评分", ge=1, le=9)

```





请求体参数：

```
{
  "patient_info": {
    "age": 45,
    "gender": "女",
    "pregnancy_status": "未怀孕",
    "allergies": ["青霉素过敏"],
    "comorbidities": ["高血压"],
    "physical_examination": "体温36.8℃，血压130/85mmHg，心肺听诊正常"
  },
  "clinical_context": {
    "department": "内科",
    "chief_complaint": "45岁女性，慢性反复头痛3年，无神经系统异常体征。",
    "medical_history": "高血压病史3年，规律服药",
    "present_illness": "一周前无明显诱因出现头痛、头晕，伴耳鸣",
    "diagnosis": "原发性高血压",
    "symptom_duration": "1周",
    "symptom_severity": "中度"
  },
  "retrieval_strategy": {
    "enable_reranking": false,
    "need_llm_recommendations": true,
    "apply_rule_filter": false,
    "top_scenarios": 1,
    "top_recommendations_per_scenario": 3,
    "similarity_threshold": 0.7,
    "min_appropriateness_rating": 5
  },
  "direct_return":true,
  "standard_query":""#该内容是用于读取xlsx里的文件内容的标准化问题。
}
```

接口响应：

1.如果direct_return是True:

```
{
    "RequestId": "200d6ec6-3378-4374-a66d-c66be3f39207",
    "Code": "Success",
    "Message": "推荐成功",
    "HostId": "127.0.0.1",
    "Data": {
        "query": "45岁女性，慢性反复头痛3年，无神经系统异常体征。 | 原发性高血压",
        "best_recommendations": [
            {
                "comprehensive_score": 80,
                "scenario_reasoning": "患者主诉为慢性反复头痛，无神经系统异常体征，符合颈源性头痛的初步评估场景。该场景推荐影像学检查以排除颈椎结构异常导致的头痛。",
                "grading_reasoning": "MR颈椎平扫对颈椎结构评估具有高敏感性和特异性，无电离辐射，适合患者进行初步评估。",
                "overall_reasoning": "患者主诉为慢性头痛伴头晕、耳鸣，无神经系统异常体征，结合高血压病史，需优先排除颈椎异常及颅内病变。考虑到患者无妊娠、无对比剂过敏史，MRI检查是安全且首选的影像学方式。推荐从颈椎MRI开始，随后根据结果决定是否进一步行颅脑MRI检查。",
                "graded_recommendations": {
                    "highly_recommended": [
                        {
                            "recommendation": {
                                "appropriateness_category": "May be appropriate (Disagreement)",
                                "contraindications": null,
                                "updated_at": "2025-10-30T15:56:39.715447",
                                "appropriateness_category_zh": "可能适宜（存在争议）",
                                "is_generated": false,
                                "reasoning_en": "There is no evidence that imaging is diagnostic for cervicogenic headache given the lack of definitive imaging diagnostic criteria and high frequency of abnormal imaging findings in asymptomatic patients [138,140,142]. Coskun et al [141] compared the conventional MRI findings of 22 patients with cervicogenic headache with those of 20 controls and found no significant difference in imaging features. Advanced MRI techniques such as diffusion tensor imaging can offer advantages in assessment of cervical nerves, which can aid in diagnosis and potentially treatment [147]. Although these MRI techniques offer great potential, they remain experimental at this point, and larger population studies are required before adoption.",
                                "confidence_score": 1.0,
                                "embedding": null,
                                "median_rating": 5.0,
                                "last_reviewed_date": null,
                                "semantic_id": "CR007537",
                                "id": 7537,
                                "reasoning_zh": "目前尚无证据表明影像学检查可确诊颈源性头痛，原因在于缺乏明确的影像学诊断标准，且无症状患者出现异常影像学表现的比例较高[138,140,142]。Coskun等[141]对比22例颈源性头痛患者与20例对照者的常规MRI结果，发现两组影像学特征无显著差异。弥散张量成像等先进MRI技术在评估颈神经方面具有优势，可能有助于诊断及潜在治疗[147]。尽管这些MRI技术前景广阔，但目前仍处于实验阶段，需开展更大规模人群研究才能投入临床应用。",
                                "evidence_level": "Expert OpinionReferences",
                                "rating_variance": null,
                                "reviewer_id": null,
                                "scenario_id": "S0772",
                                "procedure_id": "PR0541",
                                "consensus_level": null,
                                "appropriateness_rating": 5,
                                "adult_radiation_dose": "O 0 mSv",
                                "special_considerations": null,
                                "is_active": true,
                                "pediatric_radiation_dose": "O 0 mSv [ped]",
                                "pregnancy_safety": "未评估",
                                "created_at": "2025-10-30T15:56:39.715447"
                            },
                            "procedure": {
                                "modality": "MRI",
                                "icd10_code": null,
                                "id": 541,
                                "body_part": "脊柱|颈部",
                                "cpt_code": null,
                                "contrast_used": true,
                                "description_en": null,
                                "is_active": true,
                                "radiation_level": null,
                                "created_at": "2025-10-30T15:56:39.342479",
                                "exam_duration": null,
                                "description_zh": null,
                                "embedding": null,
                                "semantic_id": "PR0541",
                                "preparation_required": false,
                                "name_en": "MRI Cervical Spine Without IV Contrast",
                                "standard_code": null,
                                "name_zh": "MR颈椎(平扫",
                                "updated_at": "2025-10-30T15:56:39.342479"
                            },
                            "recommendation_level": "highly_recommended",
                            "recommendation_level_zh": "极其推荐",
                            "procedure_details": {
                                "semantic_id": "PR0541",
                                "name_zh": "MR颈椎(平扫",
                                "name_en": "MRI Cervical Spine Without IV Contrast",
                                "modality": "MRI",
                                "body_part": "脊柱|颈部",
                                "contrast_used": true,
                                "radiation_level": null,
                                "exam_duration": null,
                                "preparation_required": false,
                                "standard_code": null,
                                "description_zh": null
                            },
                            "recommendation_details": {
                                "appropriateness_rating": 5,
                                "appropriateness_category_zh": "可能适宜（存在争议）",
                                "evidence_level": "Expert OpinionReferences",
                                "consensus_level": null,
                                "adult_radiation_dose": "O 0 mSv",
                                "pediatric_radiation_dose": "O 0 mSv [ped]",
                                "pregnancy_safety": "未评估",
                                "contraindications": null,
                                "reasoning_zh": "目前尚无证据表明影像学检查可确诊颈源性头痛，原因在于缺乏明确的影像学诊断标准，且无症状患者出现异常影像学表现的比例较高[138,140,142]。Coskun等[141]对比22例颈源性头痛患者与20例对照者的常规MRI结果，发现两组影像学特征无显著差异。弥散张量成像等先进MRI技术在评估颈神经方面具有优势，可能有助于诊断及潜在治疗[147]。尽管这些MRI技术前景广阔，但目前仍处于实验阶段，需开展更大规模人群研究才能投入临床应用。",
                                "special_considerations": null
                            }
                        }
                    ],
                    "recommended": [],
                    "less_recommended": []
                },
                "recommendation_summary": {
                    "highly_recommended_count": 1,
                    "recommended_count": 0,
                    "less_recommended_count": 0,
                    "total_recommendations": 1
                },
                "final_choices": [
                    "MR颈椎(平扫)"
                ],
                "scenario_metadata": {
                    "scenario_id": "S0772",
                    "description": "成人。疑似颈源性头痛。无神经功能缺损。初始影像学检查。",
                    "panel": "神经内科",
                    "patient_population": null,
                    "clinical_context": null,
                    "original_index": 1
                }
            },
            {
                "comprehensive_score": 75,
                "scenario_reasoning": "患者主诉为头痛伴头晕、耳鸣，虽无明确警示征，但考虑到高血压病史，需排除颅内病变，如脑出血、脑梗死或占位性病变。",
                "grading_reasoning": "MR颅脑平扫+增强对颅内病变的检测具有高敏感性和特异性，尤其适合排除占位性病变或血管异常。CT颅脑平扫可作为快速替代方案。",
                "overall_reasoning": "患者主诉为慢性头痛伴头晕、耳鸣，无神经系统异常体征，结合高血压病史，需优先排除颈椎异常及颅内病变。考虑到患者无妊娠、无对比剂过敏史，MRI检查是安全且首选的影像学方式。推荐从颈椎MRI开始，随后根据结果决定是否进一步行颅脑MRI检查。",
                "graded_recommendations": {
                    "highly_recommended": [
                        {
                            "recommendation": {
                                "appropriateness_category": "Usually appropriate",
                                "contraindications": null,
                                "updated_at": "2025-10-30T15:56:39.715447",
                                "appropriateness_category_zh": "通常适宜",
                                "is_generated": false,
                                "reasoning_en": "MRI head without and with IV contrast is most useful in the initial evaluation of suspected SIH. Suggestive imaging features of SIH are best visualized on MRI head without and with IV contrast and include qualitative signs (engorgement of venous sinuses, pachymeningeal enhancement, midbrain descent, superficial siderosis, subdural hygroma or hematoma, and convex superior surface of the pituitary) and quantitative signs (pituitary height, pontomesencephalic angle, suprasellar cistern, prepontine cistern, midbrain descent, venous-hinge angle, mamillopontine angle, tonsillar descent, and area cavum veli interpositi) [16,25,26]. The cumulative presence of these intracranial findings has been shown to correlate with the likelihood of finding a spinal leak source [16].",
                                "confidence_score": 1.0,
                                "embedding": null,
                                "median_rating": 9.0,
                                "last_reviewed_date": null,
                                "semantic_id": "CR008882",
                                "id": 8882,
                                "reasoning_zh": "头颅MRI平扫+增强扫描对疑似自发性低颅压（SIH）的初步评估最为有效。SIH的特征性影像学表现在头颅MRI平扫+增强扫描中显示最佳，包括定性征象（静脉窦扩张、硬脑膜强化、中脑下沉、浅表含铁血黄素沉积、硬膜下积液或血肿以及垂体上表面凸起）和定量征象（垂体高度、桥脑中脑角、鞍上池、桥前池、中脑下沉、静脉铰链角、乳头体桥脑角、小脑扁桃体下疝及中间帆腔面积）[16,25,26]。研究证实这些颅内表现的累积出现与发现脊髓脑脊液漏源的概率具有相关性[16]。",
                                "evidence_level": "StrongReferences",
                                "rating_variance": null,
                                "reviewer_id": null,
                                "scenario_id": "S0845",
                                "procedure_id": "PR0031",
                                "consensus_level": null,
                                "appropriateness_rating": 9,
                                "adult_radiation_dose": "O 0 mSv",
                                "special_considerations": null,
                                "is_active": true,
                                "pediatric_radiation_dose": "O 0 mSv [ped]",
                                "pregnancy_safety": "未评估",
                                "created_at": "2025-10-30T15:56:39.715447"
                            },
                            "procedure": {
                                "modality": "MRI",
                                "icd10_code": null,
                                "id": 31,
                                "body_part": "头部",
                                "cpt_code": null,
                                "contrast_used": true,
                                "description_en": null,
                                "is_active": true,
                                "radiation_level": null,
                                "created_at": "2025-10-30T15:56:39.342479",
                                "exam_duration": null,
                                "description_zh": null,
                                "embedding": null,
                                "semantic_id": "PR0031",
                                "preparation_required": false,
                                "name_en": "MRI Head Without and With IV Contrast",
                                "standard_code": null,
                                "name_zh": "MR颅脑(平扫+增强)",
                                "updated_at": "2025-10-30T15:56:39.342479"
                            },
                            "recommendation_level": "highly_recommended",
                            "recommendation_level_zh": "极其推荐",
                            "procedure_details": {
                                "semantic_id": "PR0031",
                                "name_zh": "MR颅脑(平扫+增强)",
                                "name_en": "MRI Head Without and With IV Contrast",
                                "modality": "MRI",
                                "body_part": "头部",
                                "contrast_used": true,
                                "radiation_level": null,
                                "exam_duration": null,
                                "preparation_required": false,
                                "standard_code": null,
                                "description_zh": null
                            },
                            "recommendation_details": {
                                "appropriateness_rating": 9,
                                "appropriateness_category_zh": "通常适宜",
                                "evidence_level": "StrongReferences",
                                "consensus_level": null,
                                "adult_radiation_dose": "O 0 mSv",
                                "pediatric_radiation_dose": "O 0 mSv [ped]",
                                "pregnancy_safety": "未评估",
                                "contraindications": null,
                                "reasoning_zh": "头颅MRI平扫+增强扫描对疑似自发性低颅压（SIH）的初步评估最为有效。SIH的特征性影像学表现在头颅MRI平扫+增强扫描中显示最佳，包括定性征象（静脉窦扩张、硬脑膜强化、中脑下沉、浅表含铁血黄素沉积、硬膜下积液或血肿以及垂体上表面凸起）和定量征象（垂体高度、桥脑中脑角、鞍上池、桥前池、中脑下沉、静脉铰链角、乳头体桥脑角、小脑扁桃体下疝及中间帆腔面积）[16,25,26]。研究证实这些颅内表现的累积出现与发现脊髓脑脊液漏源的概率具有相关性[16]。",
                                "special_considerations": null
                            }
                        }
                    ],
                    "recommended": [
                        {
                            "recommendation": {
                                "appropriateness_category": "Usually appropriate",
                                "contraindications": null,
                                "updated_at": "2025-10-30T15:56:39.715447",
                                "appropriateness_category_zh": "通常适宜",
                                "is_generated": false,
                                "reasoning_en": "MRI complete spine without IV contrast optimized with fluid sensitive sequences is most useful in the initial evaluation of suspected SIH, particularly when performed with 3-D T2-weighted fat saturated sequences, which increases sensitivity for detecting fluid collections outside of the thecal sac [52]. This examination can detect with a high degree of accuracy the presence of epidural fluid collections and meningeal diverticula that can inform positioning and regions of interest for subsequent CSF leak localization imaging examinations, such as dynamic CT myelogram complete spine and digital subtraction myelography complete spine [25,34-36].",
                                "confidence_score": 1.0,
                                "embedding": null,
                                "median_rating": 8.0,
                                "last_reviewed_date": null,
                                "semantic_id": "CR008883",
                                "id": 8883,
                                "reasoning_zh": "不注射静脉造影剂、采用液体敏感序列优化的全脊柱MRI检查对疑似自发性低颅压（SIH）的初步评估最为有用，尤其当联合三维T2加权脂肪抑制序列时，可显著提高对硬膜囊外积液检出的敏感性[52]。该检查能高度准确地发现硬膜外积液和脑膜憩室，这些发现可为后续脑脊液漏定位检查（如动态CT脊髓造影全脊柱检查和数字减影脊髓造影全脊柱检查）的体位选择和感兴趣区划定提供依据[25,34-36]。",
                                "evidence_level": "StrongReferences",
                                "rating_variance": null,
                                "reviewer_id": null,
                                "scenario_id": "S0845",
                                "procedure_id": "PR0709",
                                "consensus_level": null,
                                "appropriateness_rating": 8,
                                "adult_radiation_dose": "O 0 mSv",
                                "special_considerations": null,
                                "is_active": true,
                                "pediatric_radiation_dose": "O 0 mSv [ped]",
                                "pregnancy_safety": "未评估",
                                "created_at": "2025-10-30T15:56:39.715447"
                            },
                            "procedure": {
                                "modality": "MRI",
                                "icd10_code": null,
                                "id": 709,
                                "body_part": "脊柱",
                                "cpt_code": null,
                                "contrast_used": false,
                                "description_en": null,
                                "is_active": true,
                                "radiation_level": null,
                                "created_at": "2025-10-30T15:56:39.342479",
                                "exam_duration": null,
                                "description_zh": null,
                                "embedding": null,
                                "semantic_id": "PR0709",
                                "preparation_required": false,
                                "name_en": "MRI Complete Spine Without IV Contrast",
                                "standard_code": null,
                                "name_zh": "MR全脊柱(平扫)",
                                "updated_at": "2025-10-30T15:56:39.342479"
                            },
                            "recommendation_level": "recommended",
                            "recommendation_level_zh": "推荐",
                            "procedure_details": {
                                "semantic_id": "PR0709",
                                "name_zh": "MR全脊柱(平扫)",
                                "name_en": "MRI Complete Spine Without IV Contrast",
                                "modality": "MRI",
                                "body_part": "脊柱",
                                "contrast_used": false,
                                "radiation_level": null,
                                "exam_duration": null,
                                "preparation_required": false,
                                "standard_code": null,
                                "description_zh": null
                            },
                            "recommendation_details": {
                                "appropriateness_rating": 8,
                                "appropriateness_category_zh": "通常适宜",
                                "evidence_level": "StrongReferences",
                                "consensus_level": null,
                                "adult_radiation_dose": "O 0 mSv",
                                "pediatric_radiation_dose": "O 0 mSv [ped]",
                                "pregnancy_safety": "未评估",
                                "contraindications": null,
                                "reasoning_zh": "不注射静脉造影剂、采用液体敏感序列优化的全脊柱MRI检查对疑似自发性低颅压（SIH）的初步评估最为有用，尤其当联合三维T2加权脂肪抑制序列时，可显著提高对硬膜囊外积液检出的敏感性[52]。该检查能高度准确地发现硬膜外积液和脑膜憩室，这些发现可为后续脑脊液漏定位检查（如动态CT脊髓造影全脊柱检查和数字减影脊髓造影全脊柱检查）的体位选择和感兴趣区划定提供依据[25,34-36]。",
                                "special_considerations": null
                            }
                        },
                        {
                            "recommendation": {
                                "appropriateness_category": "Usually appropriate",
                                "contraindications": null,
                                "updated_at": "2025-10-30T15:56:39.715447",
                                "appropriateness_category_zh": "通常适宜",
                                "is_generated": false,
                                "reasoning_en": "MRI complete spine without and with IV contrast can be useful in the initial evaluation of suspected SIH. The noncontrast component of this examination optimized with fluid sensitive sequences is most useful, particularly when performed with 3-D T2-weighted fat saturated sequences, which increases sensitivity for detecting fluid collections outside of the thecal sac [52]. It can detect with a high degree of accuracy the presence of epidural fluid collections and meningeal diverticula that can inform positioning and regions of interest for subsequent CSF leak localization imaging examinations, such as dynamic CT myelogram complete spine and digital subtraction enhancement and engorged epidural venous plexus, which are also imaging features that support a diagnosis of SIH [28,29].",
                                "confidence_score": 1.0,
                                "embedding": null,
                                "median_rating": 7.0,
                                "last_reviewed_date": null,
                                "semantic_id": "CR008884",
                                "id": 8884,
                                "reasoning_zh": "无静脉注射对比剂及增强脊柱全段MRI可用于疑似自发性颅内低压（SIH）的初始评估。该检查中采用液体敏感序列优化的无对比剂扫描序列最具价值，特别是结合3D T2加权脂肪抑制序列时可提高硬膜囊外积液检出的敏感性[52]。该检查能高度准确地检测硬膜外积液和脑膜憩室的存在，从而为后续脑脊液漏定位影像检查（如动态CT脊髓造影全脊柱和数字减影脊髓造影全脊柱）的定位提供参考。增强扫描可显示硬脑膜强化及充盈的硬膜外静脉丛，这些同样是支持SIH诊断的影像学特征[28,29]。",
                                "evidence_level": "StrongReferences",
                                "rating_variance": null,
                                "reviewer_id": null,
                                "scenario_id": "S0845",
                                "procedure_id": "PR0700",
                                "consensus_level": null,
                                "appropriateness_rating": 7,
                                "adult_radiation_dose": "O 0 mSv",
                                "special_considerations": null,
                                "is_active": true,
                                "pediatric_radiation_dose": "O 0 mSv [ped]",
                                "pregnancy_safety": "未评估",
                                "created_at": "2025-10-30T15:56:39.715447"
                            },
                            "procedure": {
                                "modality": "MRI",
                                "icd10_code": null,
                                "id": 700,
                                "body_part": "脊柱",
                                "cpt_code": null,
                                "contrast_used": true,
                                "description_en": null,
                                "is_active": true,
                                "radiation_level": null,
                                "created_at": "2025-10-30T15:56:39.342479",
                                "exam_duration": null,
                                "description_zh": null,
                                "embedding": null,
                                "semantic_id": "PR0700",
                                "preparation_required": false,
                                "name_en": "MRI Complete Spine Without and With IV Contrast",
                                "standard_code": null,
                                "name_zh": "MR全脊柱(平扫+增强)",
                                "updated_at": "2025-10-30T15:56:39.342479"
                            },
                            "recommendation_level": "recommended",
                            "recommendation_level_zh": "推荐",
                            "procedure_details": {
                                "semantic_id": "PR0700",
                                "name_zh": "MR全脊柱(平扫+增强)",
                                "name_en": "MRI Complete Spine Without and With IV Contrast",
                                "modality": "MRI",
                                "body_part": "脊柱",
                                "contrast_used": true,
                                "radiation_level": null,
                                "exam_duration": null,
                                "preparation_required": false,
                                "standard_code": null,
                                "description_zh": null
                            },
                            "recommendation_details": {
                                "appropriateness_rating": 7,
                                "appropriateness_category_zh": "通常适宜",
                                "evidence_level": "StrongReferences",
                                "consensus_level": null,
                                "adult_radiation_dose": "O 0 mSv",
                                "pediatric_radiation_dose": "O 0 mSv [ped]",
                                "pregnancy_safety": "未评估",
                                "contraindications": null,
                                "reasoning_zh": "无静脉注射对比剂及增强脊柱全段MRI可用于疑似自发性颅内低压（SIH）的初始评估。该检查中采用液体敏感序列优化的无对比剂扫描序列最具价值，特别是结合3D T2加权脂肪抑制序列时可提高硬膜囊外积液检出的敏感性[52]。该检查能高度准确地检测硬膜外积液和脑膜憩室的存在，从而为后续脑脊液漏定位影像检查（如动态CT脊髓造影全脊柱和数字减影脊髓造影全脊柱）的定位提供参考。增强扫描可显示硬脑膜强化及充盈的硬膜外静脉丛，这些同样是支持SIH诊断的影像学特征[28,29]。",
                                "special_considerations": null
                            }
                        }
                    ],
                    "less_recommended": []
                },
                "recommendation_summary": {
                    "highly_recommended_count": 1,
                    "recommended_count": 2,
                    "less_recommended_count": 0,
                    "total_recommendations": 4
                },
                "final_choices": [
                    "MR颅脑(平扫+增强)"
                ],
                "scenario_metadata": {
                    "scenario_id": "S0827",
                    "description": "成人。无近期可能导致脑脊液漏的脊柱干预史，疑似颅内低压所致体位性头痛。初始影像学检查。",
                    "panel": "神经内科",
                    "patient_population": null,
                    "clinical_context": null,
                    "original_index": 2
                }
            },
            {
                "comprehensive_score": 70,
                "scenario_reasoning": "患者主诉中包含头晕，虽无眩晕或共济失调，但头晕可能与中枢神经系统疾病相关，需进行初步影像学评估以排除结构性病变。",
                "grading_reasoning": "MR颅脑平扫对脑部结构异常的检测具有较高价值，且无电离辐射，适合用于头晕的初步评估。",
                "overall_reasoning": "患者主诉为慢性头痛伴头晕、耳鸣，无神经系统异常体征，结合高血压病史，需优先排除颈椎异常及颅内病变。考虑到患者无妊娠、无对比剂过敏史，MRI检查是安全且首选的影像学方式。推荐从颈椎MRI开始，随后根据结果决定是否进一步行颅脑MRI检查。",
                "graded_recommendations": {
                    "highly_recommended": [],
                    "recommended": [
                        {
                            "recommendation": {
                                "appropriateness_category": "Usually appropriate",
                                "contraindications": null,
                                "updated_at": "2025-10-30T15:56:39.715447",
                                "appropriateness_category_zh": "通常适宜",
                                "is_generated": false,
                                "reasoning_en": "MRI is the most sensitive imaging modality for the assessment of soft tissue abnormalities, including cervical spine soft tissues [1,46]. Also, MRI offers high spatial resolution [67]. Therefore, MRI has become the modality of choice for the assessment of suspected nerve root impingement in patients with chronic cervical radiculopathy [67]. In a 1998 retrospective study of 34 patients with clinically diagnosed cervical radiculopathy and subsequent surgery, Brown et al [68] reported that preoperative MRI correctly predicted 88% of the lesions as opposed to 81% for CT myelography, 57% for plain myelography, and 50% for CT. These findings continue to hold true in more recent studies comparing CT myelography and MRI in cervical spine degenerative disorders for the detection of disc abnormality and nerve root compression [69]. However, as noted previously, MRI demonstrates a frequent rate of false-negative and false-positive findings [55]. Also, MRI is frequently positive in asymptomatic patients, detected abnormalities are not always associated with symptoms severity or outcomes [47,60], and abnormal levels on MRI do not always correspond to abnormal clinical-physical examination levels [70]. In a study of 98 patients with cervical radiculopathy, the agreement between patients’ pain drawing and MRI findings for segmental level was poor, and the interclinical agreement was fair to moderate [155,156]. However, the recent development of newer sequences and reconstructions offer promising ability to overcome such limitations by improving the assessment of osseous nerve root compression, improving the visualization of nerve roots, and increasing the correlation with surgical findings [157-160].",
                                "confidence_score": 1.0,
                                "embedding": null,
                                "median_rating": 7.0,
                                "last_reviewed_date": null,
                                "semantic_id": "CR007568",
                                "id": 7568,
                                "reasoning_zh": "MRI是评估软组织异常（包括颈椎软组织）最敏感的影像学检查方式[1,46]。此外，MRI具有较高的空间分辨率[67]。因此，MRI已成为评估慢性颈神经根病患者疑似神经根受压的首选检查方法[67]。Brown等人在1998年对34例临床诊断为颈神经根病并接受手术治疗的患者进行的回顾性研究中报告，术前MRI对病变的准确预测率为88%，而CT脊髓造影为81%，普通脊髓造影为57%，CT为50%[68]。这些发现在近期比较CT脊髓造影与MRI对颈椎退行性疾病中椎间盘异常和神经根压迫检测的研究中仍然成立[69]。然而，如前所述，MRI检查存在较高的假阴性和假阳性结果发生率[55]。此外，MRI在无症状患者中常呈阳性表现，检测到的异常并不总是与症状严重程度或预后相关[47,60]，且MRI显示的异常节段与临床体检异常节段并不总是一致[70]。一项针对98例颈神经根病患者的研究显示，患者疼痛分布图与MRI节段定位的一致性较差，临床间一致性仅为一般至中等水平[155,156]。不过，随着新序列和重建技术的最新发展，通过改善骨性神经根压迫评估、优化神经根可视化效果以及提高与手术结果的相关性，这些技术有望突破上述局限性[157-160]。",
                                "evidence_level": "StrongReferences",
                                "rating_variance": null,
                                "reviewer_id": null,
                                "scenario_id": "S0774",
                                "procedure_id": "PR0541",
                                "consensus_level": null,
                                "appropriateness_rating": 7,
                                "adult_radiation_dose": "O 0 mSv",
                                "special_considerations": null,
                                "is_active": true,
                                "pediatric_radiation_dose": "O 0 mSv [ped]",
                                "pregnancy_safety": "未评估",
                                "created_at": "2025-10-30T15:56:39.715447"
                            },
                            "procedure": {
                                "modality": "MRI",
                                "icd10_code": null,
                                "id": 541,
                                "body_part": "脊柱|颈部",
                                "cpt_code": null,
                                "contrast_used": true,
                                "description_en": null,
                                "is_active": true,
                                "radiation_level": null,
                                "created_at": "2025-10-30T15:56:39.342479",
                                "exam_duration": null,
                                "description_zh": null,
                                "embedding": null,
                                "semantic_id": "PR0541",
                                "preparation_required": false,
                                "name_en": "MRI Cervical Spine Without IV Contrast",
                                "standard_code": null,
                                "name_zh": "MR颈椎(平扫",
                                "updated_at": "2025-10-30T15:56:39.342479"
                            },
                            "recommendation_level": "recommended",
                            "recommendation_level_zh": "推荐",
                            "procedure_details": {
                                "semantic_id": "PR0541",
                                "name_zh": "MR颈椎(平扫",
                                "name_en": "MRI Cervical Spine Without IV Contrast",
                                "modality": "MRI",
                                "body_part": "脊柱|颈部",
                                "contrast_used": true,
                                "radiation_level": null,
                                "exam_duration": null,
                                "preparation_required": false,
                                "standard_code": null,
                                "description_zh": null
                            },
                            "recommendation_details": {
                                "appropriateness_rating": 7,
                                "appropriateness_category_zh": "通常适宜",
                                "evidence_level": "StrongReferences",
                                "consensus_level": null,
                                "adult_radiation_dose": "O 0 mSv",
                                "pediatric_radiation_dose": "O 0 mSv [ped]",
                                "pregnancy_safety": "未评估",
                                "contraindications": null,
                                "reasoning_zh": "MRI是评估软组织异常（包括颈椎软组织）最敏感的影像学检查方式[1,46]。此外，MRI具有较高的空间分辨率[67]。因此，MRI已成为评估慢性颈神经根病患者疑似神经根受压的首选检查方法[67]。Brown等人在1998年对34例临床诊断为颈神经根病并接受手术治疗的患者进行的回顾性研究中报告，术前MRI对病变的准确预测率为88%，而CT脊髓造影为81%，普通脊髓造影为57%，CT为50%[68]。这些发现在近期比较CT脊髓造影与MRI对颈椎退行性疾病中椎间盘异常和神经根压迫检测的研究中仍然成立[69]。然而，如前所述，MRI检查存在较高的假阴性和假阳性结果发生率[55]。此外，MRI在无症状患者中常呈阳性表现，检测到的异常并不总是与症状严重程度或预后相关[47,60]，且MRI显示的异常节段与临床体检异常节段并不总是一致[70]。一项针对98例颈神经根病患者的研究显示，患者疼痛分布图与MRI节段定位的一致性较差，临床间一致性仅为一般至中等水平[155,156]。不过，随着新序列和重建技术的最新发展，通过改善骨性神经根压迫评估、优化神经根可视化效果以及提高与手术结果的相关性，这些技术有望突破上述局限性[157-160]。",
                                "special_considerations": null
                            }
                        }
                    ],
                    "less_recommended": []
                },
                "recommendation_summary": {
                    "highly_recommended_count": 0,
                    "recommended_count": 1,
                    "less_recommended_count": 0,
                    "total_recommendations": 3
                },
                "final_choices": [
                    "MR颅脑(平扫)"
                ],
                "scenario_metadata": {
                    "scenario_id": "S0810",
                    "description": "成人。慢性颈痛伴神经根病。无外伤或“危险信号”。初始影像学检查。",
                    "panel": "神经内科",
                    "patient_population": null,
                    "clinical_context": null,
                    "original_index": 3
                }
            }
        ],
        "processing_time_ms": 24962,
        "model_used": null,
        "reranker_model_used": null,
        "similarity_threshold": 0.7
    },
    "Success": true
}
```

2.如果direct_return是False:

```
{
    "RequestId": "200d6ec6-3378-4374-a66d-c66be3f39207",
    "Code": "Success",
    "Message": "推荐成功",
    "HostId": "127.0.0.1",
    "Data": {
        "query": "45岁女性，慢性反复头痛3年，无神经系统异常体征。 | 原发性高血压",
        "best_recommendations": “推荐项目：颅脑平扫、颅脑平扫（增强）、ct平扫。
                                 推荐理由：.......
        
        ”
          
        "processing_time_ms": 24962,
        "model_used": null,
        "reranker_model_used": null,
        "similarity_threshold": 0.7
    },
    "Success": true
}
```

#### 2.第二个接口的url是：http://203.83.233.236:5188/api/v1/acrac-code/recommend

该接口与第一个接口的参数一样，只不过是不同的实现形式，该接口的入参和输出都与第一个接口一样。

#### 3.第三个接口的url是：http://203.83.233.236:5189/api/v1/acrac/rag-llm/intelligent-recommendation

该接口的入参：

```
{
  "clinical_query": "男，35岁，头疼，头晕一周",
  "include_raw_data": false,
  "debug_mode": false,
  "top_scenarios": 3,
  "top_recommendations_per_scenario": 3,
  "show_reasoning": true,
  "similarity_threshold": 0.7,
  "compute_ragas": false,
  "ground_truth": "string"
}
```

该接口的输出：

```
{
  "success": true,
  "query": "男，35岁，头疼，头晕一周",
  "message": null,
  "llm_recommendations": {
    "recommendations": [
      {
        "rank": 1,
        "procedure_name": "MR颅脑(平扫+DTI)",
        "modality": "MRI",
        "appropriateness_rating": "8/9",
        "recommendation_reason": "全面评估脑部结构和功能",
        "clinical_considerations": "适用于年轻患者，无明显禁忌症"
      },
      {
        "rank": 2,
        "procedure_name": "CT颅脑(增强)",
        "modality": "CT",
        "appropriateness_rating": "7/9",
        "recommendation_reason": "快速获取脑部解剖结构信息",
        "clinical_considerations": "适用于需要快速诊断的情况"
      },
      {
        "rank": 3,
        "procedure_name": "MR颅脑(增强)，MR头颈部动脉血管成像(CE-MRA)",
        "modality": "MRI",
        "appropriateness_rating": "6/9",
        "recommendation_reason": "详细评估脑血管情况",
        "clinical_considerations": "适用于怀疑血管病变的情况"
      }
    ],
    "summary": "推荐使用MRI进行平扫和DTI检查，以全面评估脑部结构和功能。CT增强检查作为备选方案，适用于需要快速诊断的情况。MR增强和CE-MRA检查用于详细评估脑血管情况。",
    "no_rag": true,
    "rag_note": "无RAG模式：基于医生专业经验生成"
  },
  "scenarios": null,
  "scenarios_with_recommendations": null,
  "contexts": [
    "成人。慢性复发性眩晕。伴其他脑干神经功能缺损。初始影像学检查。",
    "成人。短暂发作性眩晕。由特定头位变动诱发（如DixHallpike手法）。初始影像学检查。",
    "成人。急性持续性眩晕。神经系统检查正常且HINTS检查提示周围性眩晕。初始影像学检查。"
  ],
  "processing_time_ms": 3980,
  "model_used": "qwen2.5-instruct",
  "embedding_model_used": "bge-m3",
  "reranker_model_used": "BAAI/bge-reranker-v2-m3",
  "similarity_threshold": 0.7,
  "max_similarity": 0.6133932288469927,
  "is_low_similarity_mode": true,
  "llm_raw_response": null,
  "debug_info": null,
  "trace": null
}
```

#### 4 .第四个接口的url是：http://203.83.233.236:5187/rimagai/checkitem/recommend_item_with_reason

接口参数：

```
{
  "session_id": "1",
  "patient_id": "1",
  "doctor_id": "1",
  "department": "神经科",
  "source": "127.0.0.1",
  "patient_sex": "男",
  "patient_age": "35岁",
  "clinic_info": "头疼，头晕一周",
  "diagnose_name": "无",
  "abstract_history": "无",
  "recommend_count": 3
}
```



接口响应：

```
data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "推荐", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "理由", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "：\n", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "- MR颅脑", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "（平扫）", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "能够提供高分辨率", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "的软组织对比", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "度，有助于发现", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "脑内微小", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "结构异常或病变", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "，如肿瘤、", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "炎症或血管异常", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "。\n- 该", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "检查无需使用放射", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "线，对于需要", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "多次随访观察", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "的患者更为安全", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "。\n- 能", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "够全面评估脑", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "部结构，包括", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "脑干和小", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "脑等部位，", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "这些区域可能与", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "患者的头痛和头晕", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "症状相关。\n-", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": " 对于检测脑", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "内出血、梗", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "塞或其他代谢性疾病", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "具有较高的敏感性和", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "特异性，有助于", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "早期诊断和治疗", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "。", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "注意事项"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "：\n"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "-"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": " 检查"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "前需去除身"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "上的金属物品，"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "如首饰、眼镜"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "等\n- 如"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "有幽闭恐惧"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "症，请提前告知"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "医生\n- "}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "检查过程中"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "需保持静止"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "，避免影响成"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颅脑(平扫)", "reason": "", "cautions": "像质量"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "推荐", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "理由", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "：\n", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "- 可以", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "清晰显示颈椎结构", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "及周围软组织", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "情况，有助于发现", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "椎间盘突出", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "或颈椎退行", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "性变等可能", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "引起头痛头晕的原因", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "。\n- MRI对", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "神经根和脊", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "髓的成像", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "效果优于CT，", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "能够更准确地", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "评估是否存在神经压迫", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "情况。\n- ", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "无需使用对比剂", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "即可获得高质量图像", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "，减少潜在的", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "过敏反应风险，", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "适合初次筛查和", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "诊断。", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "注意事项"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "：\n"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "-"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": " 检查"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "前需去除所有"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "金属物品，如"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "首饰、发夹"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "等\n- 如"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "有幽闭恐惧"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "症，请提前告知"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "医生\n- "}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "检查过程中"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "需保持静止"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "，避免影响成"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* MR颈椎(平扫)", "reason": "", "cautions": "像质量"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "推荐", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "理由", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "：\n", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "- 脑", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "电图能够检测", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "大脑电活动的变化", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "，对于评估是否存在", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "癫痫等可能导致头痛", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "头晕的疾病具有", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "重要价值。\n-", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": " 对于非结构性", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "原因引起的头痛头晕", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "，如某些类型的", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "偏头痛或功能性", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "头痛，EEG", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "可以帮助排除其他潜在", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "的神经系统问题。\n", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "- 作为一种无", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "创性检查手段", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "，EEG对", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "患者友好，可以", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "作为初步筛查工具", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "，帮助医生决定", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "是否需要进一步进行", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "影像学检查。", "cautions": ""}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": "注意事项"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": "：\n"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": "-"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": " 检查"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": "前避免摄入咖啡"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": "因和酒精\n"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": "- 保持头皮"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": "清洁，不要使用"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": "发胶等定"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": "型产品\n-"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": " 检查"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": "时需放松身体"}, "finish": 0}

data:{"code": 0, "message": "success", "data": {"check_item_name": "* EEG (脑电图)", "reason": "", "cautions": "，尽量减少移动"}, "finish": 0}

data:{"code": 0, "message": "success", "data": "", "finish": 1}

```



## 评估接口

### POST 评估推荐系统

POST /api/v1/evaluate-recommend

实现单个评估推荐系统的命中率和性能

> Body 请求参数 (multipart/form-data)

```form
file: [文件] (可选，包含临床场景和标准答案，当上传文件后，除了top_scenarios、top_recommendations_per_scenario、similarity_threshold、min_appropriateness_rating，以及endpoint其他字段全部隐藏。)

endpoint: "recommend" | "recommend-simple"|"intelligent-recommendation"|"recommend_item_with_reason"(必选，该字段默认选择recommend-simple)

standard_query: string (可选，该字段一旦填写，除了top_scenarios、top_recommendations_per_scenario、similarity_threshold、min_appropriateness_rating这四个字段，其他字段全部隐藏不可填写。该字段是recommend或recommend-simple或intelligent-recommendation或recommend_item_with_reason的公有字段只不过对于intelligent-recommendation对应的是clinical_query，而对于recommend_item_with_reason需要用正则去匹配其请求的patient_sex，patient_age，clinic_info，diagnose_name)

patient_info: JSON字符串 (可选，只有在选择"recommend" 或"recommend-simple或recommend_item_with_reason时，该字段可以填写，其中，该字段的age对应recommend_item_with_reason的patient_age，该字段的gender对应recommend_item_with_reason的patient_sex。)

clinical_context: JSON字符串 (可选，只有在选择"recommend" 或"recommend-simple或recommend_item_with_reason时，该字段可以填写，其中，该字段的department对应recommend_item_with_reason的deparment该字段的chief_complaint对应recommend_item_with_reason的clinic_info，该字段的diagnosis对应recommend_item_with_reason的diagnose_name，该字段的medical_history+present_illness对应recommend_item_with_reason的abstract_history)

enable_reranking: boolean (可选，只有在选择"recommend" 或 "recommend-simple”才会出现，其余选择隐藏)

need_llm_recommendations: boolean (可选，只有在选择"recommend" 或 "recommend-simple”才会出现，其余选择隐藏)

apply_rule_filter: boolean (可选，只有在选择"recommend" 或"recommend-simple”才会出现，其余选择隐藏)

top_scenarios: number (必选，对应intelligent-recommendation的top_scenarios,一直出现不必隐藏,默认为3)

top_recommendations_per_scenario: number (必选，对应intelligent-recommendation的top_recommendations_per_scenario，还对应recommend_item_with_reason的recommend_count，一直出现不必隐藏,默认为3)

similarity_threshold: number (可选，对应intelligent-recommendation的similarity_threshold，一直出现不必隐藏，默认为0.6或0.7)

min_appropriateness_rating: number (可选，一直出现不必隐藏,默认为5)

include_raw_data: boolean(可选，该参数为intelligent-recommendation的参数，在选择intelligent-recommendation才会出现),
debug_mode: boolean(可选，该参数为intelligent-recommendation的参数，在选择intelligent-recommendation才会出现),
show_reasoning: boolean(可选，该参数为intelligent-recommendation的参数，在选择intelligent-recommendation才会出现) ,
compute_ragas:boolean(可选，该参数为intelligent-recommendation的参数，在选择intelligent-recommendation才会出现) ,
ground_truth:string (可选,该参数为intelligent-recommendation的参数，在选择intelligent-recommendation才会出现)
session_id:string (该参数为recommend_item_with_reason的参数，当复选框选择recommend_item_with_reason时才会出现，默认为字符串化的随机数)
patient_id: string (该参数为recommend_item_with_reason的参数，当复选框选择recommend_item_with_reason时才会出现，默认为字符串化的随机数),
doctor_id:string (该参数为recommend_item_with_reason的参数，当复选框选择recommend_item_with_reason时才会出现，默认为字符串化的随机数),


```

#### 请求参数说明

| 参数名                              | 类型    | 必填 | 说明                                                         |
| :---------------------------------- | :------ | :--- | :----------------------------------------------------------- |
| file                                | File    | 否   | Excel文件，包含临床场景和标准答案，当上传文件后，除了top_scenarios、top_recommendations_per_scenario、similarity_threshold、min_appropriateness_rating，以及endpoint其他字段全部隐藏。 |
| endpoint                            | string  | 是   | 评估的接口类型：recommend 或 recommend-simple或intelligent-recommendation或recommend_item_with_reason，该字段默认选择recommend-simple |
| standard\_query                     | string  | 否   | 标准问题查询，该字段是recommend、recommend-simple、intelligent-recommendation、recommend_item_with_reason的公有字段只不过对于intelligent-recommendation对应的是clinical_query，而对于recommend_item_with_reason需要用正则去匹配其请求的patient_sex，patient_age，clinic_info，diagnose_name。 |
| patient\_info                       | string  | 否   | 患者信息JSON字符串，只有在选择"recommend" 、"recommend-simple、recommend_item_with_reason时，该字段可以填写，其中，该字段的age对应recommend_item_with_reason的patient_age，该字段的gender对应recommend_item_with_reason的patient_sex。 |
| clinical\_context                   | string  | 否   | 临床上下文JSON字符串，只有在选择"recommend" 或"recommend-simple或recommend_item_with_reason时，该字段可以填写，其中，该字段的department对应recommend_item_with_reason的deparment该字段的chief_complaint对应recommend_item_with_reason的clinic_info，该字段的diagnosis对应recommend_item_with_reason的diagnose_name，该字段的medical_history+present_illness对应recommend_item_with_reason的abstract_history。 |
| enable\_reranking                   | boolean | 否   | 是否启用重排序，只有在选择"recommend" 或 "recommend-simple”才会出现，其余选择隐藏，默认是false |
| need\_llm\_recommendations          | boolean | 否   | 是否需要LLM推荐，只有在选择"recommend" 或"recommend-simple”才会出现，其余选择隐藏,默认是false |
| apply\_rule\_filter                 | boolean | 否   | 是否应用规则过滤，只有在选择"recommend" 或"recommend-simple”才会出现，其余选择隐藏,默认是false |
| top\_scenarios                      | number  | 是   | 返回的场景数量，对应intelligent-recommendation的top_scenarios,一直出现不必隐藏，默认是3 |
| top\_recommendations\_per\_scenario | number  | 是   | 每个场景的推荐数量，对应intelligent-recommendation的top_recommendations_per_scenario，还对应recommend_item_with_reason的recommend_count，一直出现不必隐藏，默认是3 |
| show\_reasoning                     | boolean | 否   | 是否显示推理过程，默认是false                                |
| include\_raw\_data                  | boolean | 否   | 是否包含原始数据，该参数为intelligent-recommendation的参数，在选择intelligent-recommendation才会出现,默认是false |
| similarity\_threshold               | number  | 否   | 相似度阈值，对应intelligent-recommendation的similarity_threshold，一直出现不必隐藏，默认是0.7 |
| min\_appropriateness\_rating        | number  | 否   | 最小适当性评分，一直出现不必隐藏，默认是5                    |
| debug_mode                          | boolean | 否   | 该参数为intelligent-recommendation的参数，在选择intelligent-recommendation才会出现,默认是false |
| compute_ragas                       | boolean | 否   | 该参数为intelligent-recommendation的参数，在选择intelligent-recommendation才会出现,默认是false |
| ground_truth                        | string  | 否   | 该参数为intelligent-recommendation的参数，在选择intelligent-recommendation才会出现 |
| session_id                          | string  | 否   | 该参数为recommend_item_with_reason的参数，当复选框选择recommend_item_with_reason时才会出现，默认为字符串化的随机数 |
| patient_id                          | string  | 否   | 该参数为recommend_item_with_reason的参数，当复选框选择recommend_item_with_reason时才会出现，默认为字符串化的随机数 |
| doctor_id                           | string  | 否   | 该参数为recommend_item_with_reason的参数，当复选框选择recommend_item_with_reason时才会出现，默认为字符串化的随机数 |

> 返回示例

```json
{
  "request_id": "req_123456",
  "code": "200",
  "message": "评估完成",
  "success": true,
  "data": {
    "overall_accuracy": 0.85,
    "combination_a": {
      "accuracy": 0.8,
      "total_samples": 100,
      "hit_samples": 80,
      "details": [
        {
          "clinical_scenario": "头痛伴发热",
          "standard_answer": "头颅CT",
          "recommendations": ["头颅CT", "血常规"],
          "hit": true,
          "processing_time_ms": 120
        }
      ]
    },
    "combination_b": {
      "accuracy": 0.9,
      "total_samples": 100,
      "hit_samples": 90,
      "details": [
        {
          "clinical_scenario": "胸痛",
          "standard_answer": "心电图",
          "recommendations": ["心电图", "胸部X光", "心肌酶谱"],
          "hit": true,
          "processing_time_ms": 150
        }
      ]
    },
    "average_processing_time_ms": 135,
    "total_samples": 100
  }
}
```

### POST 评估所有推荐系统

POST ：api/v1/evaluate-recommend/all

## 接口概述

此接口用于执行完整的推荐系统评测流程，利用线程池并发调用四个子接口并将结果保存为CSV文件，具体参数拼装的问题可以参考前一个接口。

## 请求参数

Body 请求参数 (multipart/form-data)

```

 file: [文件] (可选，包含临床场景和标准答案)，
 top_scenarios: number (必选，默认为3)

 top_recommendations_per_scenario: number (必选，默认为3)

 similarity_threshold: number (可选，默认为0.6或0.7)

 min_appropriateness_rating: number (可选，默认为5)


```

返回示例（待定，你自己决定返回数据）

```

```











| 参数名                           | 类型  | 必填 | 说明                     |
| :------------------------------- | :---- | :--- | :----------------------- |
| file                             | File  | 是   | 上传的数据文件           |
| top_scenarios                    | int   | 是   | 要提取的顶部场景数量     |
| top_recommendations_per_scenario | int   | 是   | 每个场景生成的推荐数量   |
| similarity_threshold             | float | 是   | 相关性评估的相似度阈值   |
| min_appropriateness_rating       | float | 是   | 适当性评估的最小评分阈值 |





### 返回结果



| 状态码 | 说明      | 数据模型               |
| :-- | :------ | :----------------- |
| 200 | 评估成功    | EvaluationResponse |
| 400 | 请求参数错误  | ErrorResponse      |
| 422 | 参数验证失败  | ValidationError    |
| 500 | 服务器内部错误 | ErrorResponse      |

## 评估标准

### 组合A评估

* `top_scenarios = 1`, `top_recommendations_per_scenario = 1`
* 命中条件：唯一推荐等于标准答案
* 命中率 = 命中样本数 / 总样本数

### 组合B评估

* `top_scenarios = 3`, `top_recommendations_per_scenario = 3`
* 命中条件：标准答案出现在任一场景的推荐中
* 命中率 = 命中样本数 / 总样本数

## 数据模型

### EvaluationResponse

```json
{
  "overall_accuracy": 0.85,
  "combination_a": {
    "accuracy": 0.8,
    "total_samples": 100,
    "hit_samples": 80,
    "details": [
      {
        "clinical_scenario": "string",
        "standard_answer": "string",
        "recommendations": ["string"],
        "hit": true,
        "processing_time_ms": 120
      }
    ]
  },
  "combination_b": {
    "accuracy": 0.9,
    "total_samples": 100,
    "hit_samples": 90,
    "details": [
      {
        "clinical_scenario": "string",
        "standard_answer": "string",
        "recommendations": ["string"],
        "hit": true,
        "processing_time_ms": 150
      }
    ]
  },
  "average_processing_time_ms": 135,
  "total_samples": 100
}
```

### EvaluationDetail

```json
{
  "clinical_scenario": "string",
  "standard_answer": "string",
  "recommendations": ["string"],
  "hit": true,
  "processing_time_ms": 120
}
```

### CombinationResult

```json
{
  "accuracy": 0.8,
  "total_samples": 100,
  "hit_samples": 80,
  "details": [EvaluationDetail]
}
```

### ErrorResponse

```json
{
  "request_id": "string",
  "code": "string",
  "message": "string",
  "success": false
}
```

## 前端实现要求

### 界面组件

* 文件上传区域（Antd Upload）
* 接口选择（Radio.Group：recommend / recommend-simple）
* 参数输入区域（动态显示/隐藏）
* 评估按钮
* 结果展示区域

### 显示/隐藏逻辑

1. **上传文件后**：隐藏所有参数输入区域
2. **填写standard\_query**：隐藏patient\_info和clinical\_context
3. **填写patient\_info/clinical\_context**：隐藏standard\_query
4. **非文件模式**：显示必填参数输入区域

### 结果展示

* 总体命中率统计卡片
* 组合A/B详细结果表格
* 处理时间统计
* 样本明细展示

## 技术栈

* 前端：React + TypeScript + TailwindCSS + Ant Design
* 后端：Python + FastAPI
* 文件处理：pandas + openpyxl

