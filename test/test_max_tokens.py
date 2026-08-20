#!/usr/bin/env python3
"""
快速验证 LLM 客户端的 max_tokens 参数修复
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils import load_config, load_env, setup_logging
from src.summarizer.llm_factory import LLMClientFactory


def test_max_tokens_parameter():
    """测试 max_tokens 参数"""
    print("\n" + "=" * 60)
    print("测试 max_tokens 参数支持")
    print("=" * 60)
    
    load_env()
    config = load_config()
    logger = setup_logging(config)
    
    try:
        # 创建 LLM 客户端
        llm_client = LLMClientFactory.create_client(config)
        
        print(f"\n使用 LLM 提供商: {config['llm']['provider']}")
        print(f"默认 max_tokens: {llm_client.max_tokens}")
        
        # 测试 1: 使用默认 max_tokens
        print("\n测试 1: 使用默认 max_tokens")
        prompt1 = "简单回答：什么是机器学习？（一句话）"
        response1 = llm_client.generate(prompt1)
        print(f"响应: {response1[:100]}...")
        print("✅ 测试 1 通过")
        
        # 测试 2: 指定 max_tokens
        print("\n测试 2: 指定 max_tokens=50")
        prompt2 = "简单回答：什么是深度学习？（一句话）"
        response2 = llm_client.generate(prompt2, max_tokens=50)
        print(f"响应: {response2}")
        print("✅ 测试 2 通过")
        
        # 测试 3: 指定更大的 max_tokens
        print("\n测试 3: 指定 max_tokens=3000")
        prompt3 = "列举 5 个机器学习的应用场景"
        response3 = llm_client.generate(prompt3, max_tokens=3000)
        print(f"响应: {response3[:200]}...")
        print("✅ 测试 3 通过")
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！max_tokens 参数修复成功")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_max_tokens_parameter()
    sys.exit(0 if success else 1)
