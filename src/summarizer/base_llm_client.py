"""
LLM 客户端基类

定义统一的接口供所有 LLM 提供商实现
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List


class BaseLLMClient(ABC):
    """LLM 客户端基类"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化
        
        Args:
            config: LLM 配置
        """
        self.config = config
        self.model = config.get('model', '')
        self.temperature = config.get('temperature', 0.7)
        self.max_tokens = config.get('max_tokens', 1500)
    
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = None, max_tokens: int = None) -> str:
        """生成文本
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            max_tokens: 最大生成 tokens 数（可选，覆盖默认值）
            
        Returns:
            生成的文本
        """
        pass
    
    @abstractmethod
    def generate_batch(self, prompts: List[str], system_prompt: str = None) -> List[str]:
        """批量生成文本
        
        Args:
            prompts: 用户提示词列表
            system_prompt: 系统提示词（可选）
            
        Returns:
            生成的文本列表
        """
        pass
    
    def get_provider_name(self) -> str:
        """获取提供商名称
        
        Returns:
            提供商名称
        """
        return self.__class__.__name__.replace('Client', '')
