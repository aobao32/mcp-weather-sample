# MCP系列：启动你的第一个MCP Server并与之交互

## 一、背景

### 1、为何出现了MCP

### 2、MCP和大模型Tool Use的区别

### 3、MCP架构图

### 4、MCP常用工具

python包管理 uv 

nodejs的npm

MCP Inspector

### 5、常见问题FAQ

Q：MCP是否依赖特定开发语言
A：不依赖。一般用Python和NodeJS为主。

Q：MCP是否依赖特定大模型
A：不依赖。但不同模型功能不一样。例如不是所有模型都支持compute use，或者一些模型不支持多模态，无法输入图像。

Q：MCP是否必须在运行大模型的程序一起，是否能独立部署
A：不限制，如果在本机运行，则是用哪个stdio，如果在其他机器运行，则使用HTTP方式通信

Q：MCP使用什么工具调试？
A：MCP Inspector，基于Python或者NodeJS的工具，监听本地端口`http://localhost:5173`，然后使用浏览器访问之。

## 二、使用MCP调试工具

在MacOS上安装包管理工具homebrew，并安装NodeJS软件包，以获得`npx`包管理工具。

```shell
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install node
npm install -g npm@latest
pip3 install mcp
```

启动调试工具，这里无需从Github下载源代码，可以直接启动MCP inspector。执行如下命令。

```shell
npx @modelcontextprotocol/inspector
```

可以看到返回结果如下：

```
Starting MCP inspector...
Proxy server listening on port 3000

🔍 MCP Inspector is up and running at http://localhost:5173 🚀
```

现在用浏览器访问`http://localhost:5173`。即可看到MCP Inspector的GUI界面。如下截图。

![](https://blogimg.bitipcman.com/workshop/mcp/m-01.png)

有了调试工具，现在开始开发MCP Server。

## 三、用MCP官网文档查询天气的例子构建一个MCP Server

这里以MCP官网的Get Started里边的Quickstart - For Server Developers给出的查询天气的MCP Server为例。

### 1、安装环境

安装`uv`工具。

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

创建项目并部署依赖环境。

```shell
uv init mcp-server-whether
cd mcp-server-whether
uv venv
source .venv/bin/activate
uv add "mcp[cli]" httpx
```

### 2、部署代码

编写如下代码，保存在目录`mcp-server-weather`中，文件名叫做为`weather.py`。

这段代码的MCP Server以stdio的方式运行，本身不需要监听端口，当通过stdio接收到MCP Client的请求后，自身再对外发起向`https://api.weather.gov`的访问。

```python
from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("weather")

# Constants
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"

async def make_nws_request(url: str) -> dict[str, Any] | None:
    """Make a request to the NWS API with proper error handling."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json"
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    props = feature["properties"]
    return f"""
Event: {props.get('event', 'Unknown')}
Area: {props.get('areaDesc', 'Unknown')}
Severity: {props.get('severity', 'Unknown')}
Description: {props.get('description', 'No description available')}
Instructions: {props.get('instruction', 'No specific instructions provided')}
"""

@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state. 提供美国州的天气预警

    Args:
        state: Two-letter US state code (e.g. CA, NY)
    """
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url)

    if not data or "features" not in data:
        return "Unable to fetch alerts or no alerts found."

    if not data["features"]:
        return "No active alerts for this state."

    alerts = [format_alert(feature) for feature in data["features"]]
    return "\n---\n".join(alerts)

@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """Get weather forecast for a location. 提供特定地理坐标的天气预报

    Args:
        latitude: Latitude of the location
        longitude: Longitude of the location
    """
    # First get the forecast grid endpoint
    points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url)

    if not points_data:
        return "Unable to fetch forecast data for this location."

    # Get the forecast URL from the points response
    forecast_url = points_data["properties"]["forecast"]
    forecast_data = await make_nws_request(forecast_url)

    if not forecast_data:
        return "Unable to fetch detailed forecast."

    # Format the periods into a readable forecast
    periods = forecast_data["properties"]["periods"]
    forecasts = []
    for period in periods[:5]:  # Only show next 5 periods
        forecast = f"""
{period['name']}:
Temperature: {period['temperature']}°{period['temperatureUnit']}
Wind: {period['windSpeed']} {period['windDirection']}
Forecast: {period['detailedForecast']}
"""
        forecasts.append(forecast)

    return "\n---\n".join(forecasts)

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')
```

保存退出。

### 3、开启调试

由于这个MCP Server是以stdio的方式工作，自身不监听端口，因此无法直接通过网络调试，要调试它必须借助MCP Inspector。

在上一个章节介绍了通过Node启动MCP Inspector，此外还可以通过python有的包管理两种启动inspector的命令，一是通过python。执行如下代码。

```shell
uv run mcp dev weather.py
```

返回结果如下：

```shell
Starting MCP inspector...
Proxy server listening on port 3000

🔍 MCP Inspector is up and running at http://localhost:5173 🚀
```

现在打开浏览器，访问刚才返回的地址`http://localhost:5173/`。可看到MCP Inspector界面。

在左侧选择协议位置，从下拉框中选择`Transport Type`，在`Command`里边输入`uv`，在`Arguments`参数位置，输入`run --with mcp mcp run weather.py`。然后点击`Connect`按钮。

点击页面中间上方的`Tools`标签页，在点击`List Tools`按钮，即可看到下方列出了本MCP Server的两种工具，分别叫做`get_alerts`和`get_forecast`两种方法。如下截图。

![](https://blogimg.bitipcman.com/workshop/mcp/m-02.png)

可看到查询本MCP可用的tool成功。

至此Server调试完毕，可以在终端上按`CTRL+C`键，停止刚才uv工具启动的调试。

## 四、构建一个以命令行为基础的MCP Client并连接到Server

### 1、安装环境

```shell

```

### 2、部署代码

编辑如下代码，保存在目录`mcp-client`中，文件名叫做`client.py`。

```python

```

### 3、访问MCP Server

确保本机有通过AWSCLI配置了AKSK，且AKSK具有访问Bedrock和大模型的权限。

在当前`mcp-client`目录下，执行如下命令启动MCP。

```shell
uv run client.py ../mcp-server-weather/weather.py
```

在终端窗口中，可尝试提问。

询问xxx信息，可看到返回结果如下。

至此可以看到，一个查询天气的MCP Server工作正常，且这个MCP Server使用了stdio本机调用的方式，无需监听端口，节约资源且高效。

## 五、小结

更多按照MCP协议开发的插件可参考这里：

[]()

## 六、参考文档

Quickstart - For Server Developers

[https://modelcontextprotocol.io/quickstart/server]()

Quickstart - For Client Developers

[https://modelcontextprotocol.io/quickstart/client]()

Bedrock Converse API tool use - examples

[https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-examples.html]()