# app.py - Flask流式传输对话应用（详细中文注释版）

# ===== 导入必要的库 =====
from flask import Flask, render_template, request, Response  # Flask web框架核心组件
from langchain_deepseek import ChatDeepSeek  # DeepSeek AI模型的LangChain包装器
import json  # JSON数据处理库，用于格式化SSE数据

# ===== 创建Flask应用实例 =====
app = Flask(__name__)
# Flask(__name__) 创建应用实例，__name__帮助Flask找到模板和静态文件

# ===== 初始化DeepSeek大语言模型 =====
llm = ChatDeepSeek(
    model="deepseek-chat",  # 指定使用的AI模型名称
    temperature=0.7,  # 控制输出随机性：0=确定性，1=高随机性，0.7=平衡创造性和一致性
    max_tokens=2048,  # 单次响应的最大token数，限制输出长度防止过长响应
    timeout=30.0,  # API请求超时时间（秒），防止无限等待
    max_retries=2,  # 请求失败时的最大重试次数，提高稳定性
    api_key="自己的"  # DeepSeek API密钥（实际使用时应从环境变量读取）
)

# ===== HTML格式化的系统提示词 =====
HTML_SYSTEM_PROMPT = """你是一个专业的AI助手"""


# ===== 路由定义：主页 =====
@app.route('/')
def home():
    """
    主页路由处理函数

    功能：
    - 响应根路径 '/' 的GET请求
    - 渲染聊天界面HTML模板

    返回：
    - 渲染后的chat.html页面
    """
    return render_template('chat.html')
    # render_template自动在templates/目录下查找chat.html文件


# ===== 路由定义：流式对话API =====
@app.route('/stream_chat', methods=['POST'])
def stream_chat():
    """
    流式对话API端点

    功能：
    - 接收POST请求中的用户消息
    - 调用AI模型进行流式生成
    - 以SSE格式实时返回AI响应

    请求格式：
    - Content-Type: application/x-www-form-urlencoded
    - Body: message=用户输入的消息内容

    响应格式：
    - Content-Type: text/event-stream
    - 数据格式：data: {"type": "...", "content": "..."}\n\n
    """
    try:
        # ===== 第1步：获取并验证用户输入 =====
        user_message = request.form.get('message', '').strip()
        # request.form.get()：安全获取表单数据，如果不存在则返回空字符串
        # .strip()：移除字符串首尾的空白字符

        # 控制台日志输出，便于调试和监控
        print("=" * 50)  # 分隔线，便于区分不同请求
        print(f"🌊 收到HTML流式对话请求: '{user_message}'")

        # ===== 第2步：输入验证 =====
        if not user_message:
            # 如果消息为空，立即返回错误响应
            error_response = {
                'type': 'error',
                'content': '<p style="color: red;">消息不能为空</p>'
            }
            return Response(
                f"data: {json.dumps(error_response, ensure_ascii=False)}\n\n",
                mimetype='text/event-stream'  # 即使是错误，也要保持SSE格式
            )

        # ===== 第3步：构建对话消息 =====
        messages = [
            ("system", HTML_SYSTEM_PROMPT),  # 系统提示词，定义AI的行为和输出格式
            ("human", user_message)  # 用户消息
        ]
        # LangChain消息格式：(角色, 内容) 的元组列表

        print(f"🔍 开始HTML流式生成...")

        # ===== 第4步：定义流式生成器函数 =====
        def generate():
            """
            流式数据生成器函数

            这是整个流式传输的核心函数，它：
            1. 使用yield关键字实现生成器模式
            2. 调用AI模型的stream方法获取流式响应
            3. 将AI输出格式化为SSE数据格式
            4. 实时发送数据给前端

            SSE数据格式规范：
            - 每行以 "data: " 开头
            - 数据为JSON格式的字符串
            - 每个消息以 "\n\n" 结尾
            """
            try:
                # 用于累积AI的完整响应内容
                full_content = ""

                # ===== 阶段1：发送开始信号 =====
                start_signal = {
                    'type': 'start',  # 消息类型：开始
                    'content': ''  # 开始时内容为空
                }
                yield f"data: {json.dumps(start_signal, ensure_ascii=False)}\n\n"
                # ensure_ascii=False 确保中文字符正确编码

                # ===== 阶段2：处理AI模型的流式输出 =====
                for chunk in llm.stream(messages):
                    """
                    llm.stream(messages) 返回一个生成器，每次迭代产生一个chunk
                    chunk是AI模型的部分响应，包含：
                    - content: 文本内容
                    - response_metadata: 元数据（包括完成状态）
                    """

                    # 安全提取chunk的内容
                    chunk_content = chunk.content if hasattr(chunk, 'content') else ""
                    # hasattr检查对象是否有指定属性，防止AttributeError

                    # 调试日志：显示收到的内容块
                    print(f"🔍 收到HTML chunk: '{chunk_content}'")

                    # 累积完整内容，用于最终的完成信号
                    full_content += chunk_content

                    # ===== 检查生成是否完成 =====
                    is_finished = False
                    if hasattr(chunk, 'response_metadata') and chunk.response_metadata:
                        # 检查元数据中是否包含完成原因
                        if 'finish_reason' in chunk.response_metadata:
                            is_finished = True
                            print(f"🔍 检测到结束信号: {chunk.response_metadata}")

                    # ===== 处理生成完成的情况 =====
                    if chunk_content == "" and is_finished:
                        """
                        判断生成完成的条件：
                        1. 当前chunk内容为空
                        2. 元数据中有完成标志

                        这种设计避免了仅凭内容为空就判断完成的错误
                        """
                        print(f"✅ HTML流式生成完成，总长度: {len(full_content)}")

                        # 发送完成信号
                        end_signal = {
                            'type': 'end',  # 消息类型：结束
                            'content': '',  # 结束信号内容为空
                            'full_content': full_content  # 完整的响应内容
                        }
                        yield f"data: {json.dumps(end_signal, ensure_ascii=False)}\n\n"
                        break  # 退出循环，结束生成器

                    # ===== 发送内容块 =====
                    if chunk_content:
                        """
                        只有当chunk有实际内容时才发送
                        这避免了发送空的chunk给前端
                        """
                        chunk_data = {
                            'type': 'chunk',  # 消息类型：内容块
                            'content': chunk_content  # 实际的文本内容
                        }
                        # 直接发送HTML内容，无需额外处理或转义
                        yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

            except Exception as e:
                """
                异常处理：捕获生成过程中的任何错误
                确保即使出错也能给前端发送错误信息
                """
                print(f"❌ HTML流式生成错误: {e}")
                error_html = f'<p style="color: red;">HTML流式生成错误: {str(e)}</p>'
                error_data = {
                    'type': 'error',
                    'content': error_html
                }
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

        # ===== 第5步：返回流式响应 =====
        return Response(
            generate(),  # 生成器函数作为响应体
            mimetype='text/event-stream',  # 关键：指定MIME类型为SSE
            headers={
                # ===== 核心SSE响应头 =====
                'Cache-Control': 'no-cache',  # 禁止缓存，确保数据实时性
                'Connection': 'keep-alive',  # 保持HTTP连接，避免重连开销

                # ===== 代理服务器配置 =====
                'X-Accel-Buffering': 'no',  # 禁用Nginx缓冲，立即转发数据

                # ===== CORS跨域支持 =====
                'Access-Control-Allow-Origin': '*',  # 允许所有域访问
                'Access-Control-Allow-Methods': 'POST',  # 允许POST方法
                'Access-Control-Allow-Headers': 'Content-Type'  # 允许的请求头
            }
        )

    except Exception as e:
        """
        全局异常处理：捕获整个请求处理过程中的错误
        确保任何情况下都能返回有效的SSE响应
        """
        print(f"❌ HTML流式对话错误: {e}")
        error_html = f'<p style="color: red;">HTML流式对话错误: {str(e)}</p>'
        error_response = {
            'type': 'error',
            'content': error_html
        }
        return Response(
            f"data: {json.dumps(error_response, ensure_ascii=False)}\n\n",
            mimetype='text/event-stream'
        )


# ===== 应用启动配置 =====
if __name__ == '__main__':
    """
    应用启动入口

    只有直接运行此脚本时才会执行，import时不会执行
    """
    # 启动信息输出
    print("🚀 Flask HTML流式对话应用启动...")
    print("📍 访问地址: http://127.0.0.1:5000")
    print("🌊 HTML流式传输模式")
    print("📁 HTML模板路径: templates/chat.html")
    print("🎨 支持丰富的HTML格式输出")
    print("=" * 50)

    # 启动Flask开发服务器
    app.run(
        debug=True,  # 开启调试模式：代码变更自动重启，显示详细错误信息
        host='127.0.0.1',  # 监听地址：本地回环地址
        port=5000,  # 监听端口：Flask默认端口
        threaded=True  # 启用多线程：支持并发请求处理
    )

"""
===== 代码架构总结 =====

1. 应用初始化层：
   - Flask应用创建和配置
   - AI模型初始化和参数设置
   - 系统提示词定义

2. 路由处理层：
   - 主页路由：返回静态HTML界面
   - API路由：处理流式对话请求

3. 流式处理层：
   - 生成器函数：核心流式逻辑
   - 数据格式化：SSE标准格式
   - 状态管理：开始/进行/结束状态

4. 错误处理层：
   - 输入验证：防止无效请求
   - 异常捕获：多层次错误处理
   - 错误响应：统一的错误信息格式

5. 响应配置层：
   - HTTP响应头：SSE和CORS配置
   - 缓存控制：确保实时性
   - 连接管理：保持持久连接

===== 关键技术特点 =====

1. 流式传输：使用Python生成器和SSE协议
2. 实时性：AI生成的每个token立即推送
3. 健壮性：多层异常处理确保稳定运行
4. 可扩展性：模块化设计便于功能扩展
5. 用户体验：实时反馈提升交互体验
"""