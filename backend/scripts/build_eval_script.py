import asyncio
import pandas as pd
from typing import List
import logging
from concurrent.futures import ThreadPoolExecutor
from openpyxl import load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 您的现有代码
from typing import Optional, List
from langchain_core.prompts import ChatPromptTemplate
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from backend.app.config.config import settings


class PatientInfo(BaseModel):
    """患者基本信息"""
    age: Optional[int] = Field(None, description="患者年龄", ge=0, le=150)
    gender: Optional[str] = Field(None, description="患者性别：男/女")
    pregnancy_status: Optional[str] = Field(None, description="妊娠状态：可以是妊娠期/哺乳期/非妊娠期")
    allergies: Optional[List[str]] = Field(None, description="过敏史列表")
    comorbidities: Optional[List[str]] = Field(None, description="合并症列表")
    physical_examination: Optional[str] = Field(None, description="检查报告")


class ClinicalContext(BaseModel):
    """临床上下文信息"""
    department: Optional[str] = Field(..., description="科室名称", min_length=2, max_length=50)
    chief_complaint: Optional[str] = Field(..., description="主诉", min_length=2, max_length=500)
    medical_history: Optional[str] = Field(None, description="既往病史", max_length=2000)
    present_illness: Optional[str] = Field(None, description="现病史", max_length=2000)
    diagnosis: Optional[str] = Field(None, description="医生主诊断结果", max_length=500)
    symptom_duration: Optional[str] = Field(None, description="症状持续时间")
    symptom_severity: Optional[str] = Field(None, description="症状严重程度：轻度/中度/重度")


class StructOutputPatient(BaseModel):
    patient_info: PatientInfo
    clinical_context: ClinicalContext


class LLMProcessor:
    def __init__(self):
        self.llm = ChatDeepSeek(
            model=settings.DEEPSEEK_MODEL_NAME,
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY
        ).with_structured_output(StructOutputPatient)

        self.prompt = ChatPromptTemplate.from_messages([
            ("system",
             "你是一个严格按照指令输出内容的助手，请根据提供的临床场景信息，提取并结构化患者基本信息和临床上下文信息。"),
            ("user", "这是用户的输入：{text}")
        ])

        self.chain = self.prompt | self.llm

    async def process_single_scenario(self, scenario: str) -> Optional[StructOutputPatient]:
        """处理单个临床场景"""
        try:
            if not scenario or pd.isna(scenario):
                logger.warning("遇到空的临床场景，跳过处理")
                return None

            logger.info(f"开始处理临床场景: {scenario[:50]}...")
            response = await self.chain.ainvoke({"text": scenario})
            logger.info("成功处理临床场景")
            return response

        except Exception as e:
            logger.error(f"处理临床场景时出错: {str(e)}")
            return None


class ExcelProcessor:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.llm_processor = LLMProcessor()

    def read_excel_data(self) -> pd.DataFrame:
        """读取Excel文件并进行列名转换"""
        try:
            df = pd.read_excel(self.file_path)
            logger.info(f"成功读取Excel文件，共{len(df)}行数据")

            # 列名映射：中文到英文
            column_mapping = {
                '临床场景': 'scenarios',
                '首选检查项目（标准化）': 'gold_answer'
                # 可以根据需要添加更多列名映射
            }

            # 重命名列
            df.rename(columns=column_mapping, inplace=True)

            # 确保必要的列存在
            if 'scenarios' not in df.columns:
                # 尝试找到可能的临床场景列
                possible_columns = [col for col in df.columns if '临床' in str(col) or '场景' in str(col)]
                if possible_columns:
                    df.rename(columns={possible_columns[0]: 'scenarios'}, inplace=True)
                    logger.info(f"自动映射临床场景列: {possible_columns[0]} -> scenarios")
                else:
                    raise ValueError("未找到临床场景列，请确保Excel文件包含'临床场景'列")

            logger.info(f"列名转换完成，当前列: {list(df.columns)}")
            return df

        except Exception as e:
            logger.error(f"读取Excel文件失败: {str(e)}")
            raise

    def prepare_output_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """准备输出列"""
        # 患者信息列
        patient_columns = [
            'patient_age', 'patient_gender', 'patient_pregnancy_status',
            'patient_allergies', 'patient_comorbidities', 'patient_physical_examination'
        ]

        # 临床上下文列
        clinical_columns = [
            'clinical_department', 'clinical_chief_complaint', 'clinical_medical_history',
            'clinical_present_illness', 'clinical_diagnosis', 'clinical_symptom_duration',
            'clinical_symptom_severity'
        ]

        # 添加新列（如果不存在）
        for col in patient_columns + clinical_columns:
            if col not in df.columns:
                df[col] = None

        return df

    def update_dataframe_with_result(self, df: pd.DataFrame, index: int, result: StructOutputPatient):
        """用LLM结果更新DataFrame"""
        if result is None:
            return

        try:
            # 更新患者信息
            patient = result.patient_info
            if patient:
                df.at[index, 'patient_age'] = patient.age
                df.at[index, 'patient_gender'] = patient.gender
                df.at[index, 'patient_pregnancy_status'] = patient.pregnancy_status
                df.at[index, 'patient_allergies'] = ', '.join(patient.allergies) if patient.allergies else None
                df.at[index, 'patient_comorbidities'] = ', '.join(
                    patient.comorbidities) if patient.comorbidities else None
                df.at[index, 'patient_physical_examination'] = patient.physical_examination

            # 更新临床上下文
            clinical = result.clinical_context
            if clinical:
                df.at[index, 'clinical_department'] = clinical.department
                df.at[index, 'clinical_chief_complaint'] = clinical.chief_complaint
                df.at[index, 'clinical_medical_history'] = clinical.medical_history
                df.at[index, 'clinical_present_illness'] = clinical.present_illness
                df.at[index, 'clinical_diagnosis'] = clinical.diagnosis
                df.at[index, 'clinical_symptom_duration'] = clinical.symptom_duration
                df.at[index, 'clinical_symptom_severity'] = clinical.symptom_severity

        except Exception as e:
            logger.error(f"更新DataFrame时出错 (行 {index}): {str(e)}")

    async def process_batch_concurrently(self, scenarios: List[str], max_concurrent: int = 5) -> List[
        Optional[StructOutputPatient]]:
        """并发处理一批临床场景"""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(scenario: str):
            async with semaphore:
                return await self.llm_processor.process_single_scenario(scenario)

        tasks = [process_with_semaphore(scenario) for scenario in scenarios]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常结果
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"任务执行异常: {str(result)}")
                processed_results.append(None)
            else:
                processed_results.append(result)

        return processed_results

    def save_with_proper_columns(self, df: pd.DataFrame, output_path: str):
        """保存DataFrame，确保列顺序合理"""
        # 定义列的顺序
        base_columns = ['scenarios', 'gold_answer']
        patient_columns = [
            'patient_age', 'patient_gender', 'patient_pregnancy_status',
            'patient_allergies', 'patient_comorbidities', 'patient_physical_examination'
        ]
        clinical_columns = [
            'clinical_department', 'clinical_chief_complaint', 'clinical_medical_history',
            'clinical_present_illness', 'clinical_diagnosis', 'clinical_symptom_duration',
            'clinical_symptom_severity'
        ]

        # 获取其他列（不在上述列表中的列）
        other_columns = [col for col in df.columns if col not in base_columns + patient_columns + clinical_columns]

        # 重新排列列顺序
        final_columns = base_columns + patient_columns + clinical_columns + other_columns

        # 只保留实际存在的列
        final_columns = [col for col in final_columns if col in df.columns]

        df_reordered = df[final_columns]
        df_reordered.to_excel(output_path, index=False)
        logger.info(f"文件已保存，列顺序: {final_columns}")

    async def process_excel_file(self, output_path: str = None, batch_size: int = 10, max_concurrent: int = 5):
        """处理整个Excel文件"""
        if output_path is None:
            output_path = self.file_path.replace('.xlsx', '_processed.xlsx')

        # 读取数据并转换列名
        df = self.read_excel_data()
        df = self.prepare_output_columns(df)

        # 获取所有临床场景
        scenarios = df['scenarios'].tolist()
        total_rows = len(scenarios)

        logger.info(f"开始处理 {total_rows} 行数据，批次大小: {batch_size}, 最大并发数: {max_concurrent}")

        # 分批处理
        for i in range(0, total_rows, batch_size):
            batch_end = min(i + batch_size, total_rows)
            batch_scenarios = scenarios[i:batch_end]
            batch_indices = list(range(i, batch_end))

            logger.info(
                f"处理批次 {i // batch_size + 1}/{(total_rows + batch_size - 1) // batch_size}: 行 {i + 1}-{batch_end}")

            # 并发处理当前批次
            batch_results = await self.process_batch_concurrently(batch_scenarios, max_concurrent)

            # 更新DataFrame
            for idx, result in zip(batch_indices, batch_results):
                self.update_dataframe_with_result(df, idx, result)

            # 每处理完一个批次就保存一次，防止数据丢失
            self.save_with_proper_columns(df, output_path)
            logger.info(f"已保存进度到: {output_path}")

            # 添加延迟以避免API限制
            await asyncio.sleep(1)

        logger.info(f"处理完成！结果已保存到: {output_path}")
        return df


# 使用示例
async def main():
    file_path = r"D:\code\acrac-code-v1\backend\origin_data\影像测试样例-0318-1.xlsx"

    try:
        processor = ExcelProcessor(file_path)
        await processor.process_excel_file(
            output_path=None,  # 使用默认输出路径
            batch_size=10,  # 每批处理10行
            max_concurrent=5  # 最大并发5个请求
        )
    except Exception as e:
        logger.error(f"处理失败: {str(e)}")


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())