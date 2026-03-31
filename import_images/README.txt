把洛克王国「队伍分享截图」放在这个文件夹里，
然后在 battle.py 菜单中选「5. 从图片导入队伍」，
程序会自动识别图片中的精灵名、技能名和队伍名，
并将队伍保存到队伍名册中。

支持的格式：JPG / PNG / WEBP / GIF

首次使用前请配置 API Key：
  Windows CMD:   set ANTHROPIC_API_KEY=sk-ant-...
  PowerShell:    $env:ANTHROPIC_API_KEY="sk-ant-..."
  永久设置：在「系统属性 → 环境变量」中添加 ANTHROPIC_API_KEY

图片要求：
  · 洛克王国游戏内的标准组队分享截图
  · 图中须包含 6 只精灵，每只有 4 个技能名
  · 右下角须有队伍名称（如"队伍1"）
  · 图片清晰、文字可读即可，无需额外处理
