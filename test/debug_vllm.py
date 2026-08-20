#!/usr/bin/env python3
"""
调试 vLLM 客户端初始化问题
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from openai import OpenAI

# 测试 1: 基本初始化
print("测试 1: 基本初始化")
try:
    client = OpenAI(
        api_key="EMPTY",
        base_url="http://localhost:8000/v1"
    )
    print("✅ 基本初始化成功")
except Exception as e:
    print(f"❌ 基本初始化失败: {e}")
    import traceback
    traceback.print_exc()

# 测试 2: 带 proxies 参数
print("\n测试 2: 带 proxies 参数")
try:
    client = OpenAI(
        api_key="EMPTY",
        base_url="http://localhost:8000/v1",
        proxies=None
    )
    print("✅ 带 proxies 初始化成功")
except Exception as e:
    print(f"❌ 带 proxies 初始化失败: {e}")

# 测试 3: 从配置加载
print("\n测试 3: 从配置加载客户端")
try:
    from src.utils import load_config, load_env
    from src.summarizer.vllm_client import VLLMClient
    
    load_env()
    config = load_config()
    vllm_config = config['llm']['vllm']
    
    print(f"配置内容: {vllm_config}")
    
    client = VLLMClient(vllm_config)
    print("✅ VLLMClient 初始化成功")
except Exception as e:
    print(f"❌ VLLMClient 初始化失败: {e}")
    import traceback
    traceback.print_exc()
