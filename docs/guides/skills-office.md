# Windows 技能 — Office/Outlook 自动化

*"时间不在于你拥有多少，而在于你如何使用。"* — 艾克

本模块提供 Microsoft Office 和 Outlook 的 Python 自动化技能，仅支持 **Windows 平台**。

---

## 前置依赖

### 安装依赖

```powershell
# Office 自动化
pip install python-docx openpyxl python-pptx pywin32

# 或一步安装
pip install python-docx openpyxl python-pptx pywin32
```

### 环境要求

- Windows 操作系统
- 已安装对应的 Microsoft Office 应用
- Outlook 自动化需要 Outlook 客户端运行中

> ⚠️ **注意**：本技能仅在 Windows 上可用，非 Windows 系统导入时会抛出 `OSError`。

---

## 1. Word 自动化

### 基本用法

```python
from h_agent.skills.office import Word

# 创建文档
doc = Word.create_document("output.docx")
Word.add_heading(doc, "标题", level=1)
Word.add_paragraph(doc, "这是第一段内容。")
Word.add_paragraph(doc, "这是第二段内容。")
Word.save(doc)
```

### API 概览

| 方法 | 说明 | 参数 |
|------|------|------|
| `create_document()` | 创建新文档 | `path` |
| `open_document()` | 打开现有文档 | `path` |
| `save()` | 保存文档 | `doc`, `path`（可选） |
| `add_heading()` | 添加标题 | `doc`, `text`, `level` |
| `add_paragraph()` | 添加段落 | `doc`, `text`, `style` |
| `add_table()` | 添加表格 | `doc`, `data`, `cols` |
| `set_font()` | 设置字体 | `doc`, `font_name`, `size` |
| `find_replace()` | 查找替换 | `doc`, `find`, `replace` |

### 文档格式操作

```python
# 打开文档
doc = Word.open_document("template.docx")

# 添加多级标题
Word.add_heading(doc, "第一章", level=1)
Word.add_heading(doc, "1.1 背景", level=2)

# 添加带格式的段落
para = Word.add_paragraph(doc, "这是一段**加粗**和*斜体*的文字。")

# 设置字体
Word.set_font(doc, font_name="微软雅黑", size=12)

# 添加表格
data = [
    ["姓名", "年龄", "城市"],
    ["张三", "28", "北京"],
    ["李四", "35", "上海"],
]
Word.add_table(doc, data=data, cols=3)

# 查找替换
Word.find_replace(doc, find="旧文本", replace="新文本")

# 保存
Word.save(doc, "output.docx")
```

### 注意事项

- `create_document()` 不会自动保存，需要手动调用 `save()`
- `save(doc)` 如果文档是由 `open_document()` 打开的，会覆盖原文件
- `find_replace()` 使用 Word 的内置查找替换，性能较好

---

## 2. Excel 自动化

### 基本用法

```python
from h_agent.skills.office import Excel

# 创建工作簿
wb = Excel.create_workbook("output.xlsx")

# 写入数据
Excel.write_cell(wb, "Sheet1", "A1", "姓名")
Excel.write_cell(wb, "Sheet1", "B1", "分数")
Excel.write_cell(wb, "Sheet1", "A2", "张三")
Excel.write_cell(wb, "Sheet1", "B2", "95")

# 保存
Excel.save(wb)
```

### API 概览

| 方法 | 说明 | 参数 |
|------|------|------|
| `create_workbook()` | 创建新工作簿 | `path` |
| `open_workbook()` | 打开工作簿 | `path` |
| `save()` | 保存工作簿 | `wb`, `path`（可选） |
| `write_cell()` | 写入单元格 | `wb`, `sheet`, `cell`, `value` |
| `read_cell()` | 读取单元格 | `wb`, `sheet`, `cell` |
| `add_sheet()` | 添加工作表 | `wb`, `name` |
| `write_row()` | 写入一行 | `wb`, `sheet`, `row`, `data` |
| `write_column()` | 写入一列 | `wb`, `sheet`, `col`, `data` |
| `set_formula()` | 设置公式 | `wb`, `sheet`, `cell`, `formula` |

### 批量操作

```python
# 批量写入行
data = ["Alice", 28, "Beijing"], ["Bob", 35, "Shanghai"]
for i, row in enumerate(data, start=2):
    for j, val in enumerate(row):
        Excel.write_cell(wb, "Sheet1", f"{chr(65+j)}{i}", val)

# 写入列
names = ["张三", "李四", "王五"]
Excel.write_column(wb, "Sheet1", "A", names)

# 设置公式
Excel.set_formula(wb, "Sheet1", "C1", "=SUM(B2:B10)")
Excel.set_formula(wb, "Sheet1", "D1", "=AVERAGE(B2:B10)")
```

### 注意事项

- `openpyxl` 不支持 Excel 宏（`.xlsm`），需要宏请用 `pywin32`
- 单元格坐标使用 Excel 格式（如 `A1`、`B2`）
- 大数据量（>10000 行）建议使用 `write_row` 批量操作而非逐格写入

---

## 3. PowerPoint 自动化

### 基本用法

```python
from h_agent.skills.office import PowerPoint

# 创建演示文稿
ppt = PowerPoint.create_presentation("output.pptx")

# 添加幻灯片
slide1 = PowerPoint.add_slide(ppt, "标题页")
PowerPoint.set_title(slide1, "项目汇报")
PowerPoint.add_text(slide1, "2024 年度总结", position="subtitle")

slide2 = PowerPoint.add_slide(ppt, "内容页")
PowerPoint.set_title(slide2, "工作成果")
PowerPoint.add_text(slide2, "• 完成了 5 个项目\n• 团队扩增到 10 人")

PowerPoint.save(ppt)
```

### API 概览

| 方法 | 说明 | 参数 |
|------|------|------|
| `create_presentation()` | 创建新演示文稿 | `path` |
| `open_presentation()` | 打开演示文稿 | `path` |
| `save()` | 保存 | `ppt`, `path`（可选） |
| `add_slide()` | 添加幻灯片 | `ppt`, `layout`（标题/内容等） |
| `set_title()` | 设置标题 | `slide`, `title` |
| `add_text()` | 添加文本框 | `slide`, `text`, `position` |
| `add_image()` | 添加图片 | `slide`, `image_path`, `position` |

---

## 4. Outlook 邮件自动化

### 基本用法

```python
from h_agent.skills.outlook import Mail

# 发送邮件
Mail.send_mail(
    to="recipient@example.com",
    subject="项目进度汇报",
    body="大家好，项目已进入测试阶段。",
    cc="manager@example.com"  # 可选
)

# 发送富文本邮件
Mail.send_mail(
    to="team@example.com",
    subject="会议通知",
    body="<html><body><h2>团队会议</h2><p>时间：明天下午3点</p></body></html>",
    body_type="HTML"
)
```

### API 概览

| 方法 | 说明 | 参数 |
|------|------|------|
| `send_mail()` | 发送邮件 | `to`, `subject`, `body`, `cc`, `body_type` |
| `search_emails()` | 搜索邮件 | `query`, `folder`, `limit` |
| `get_inbox()` | 获取收件箱 | `limit` |
| `mark_as_read()` | 标记已读 | `entry_id` |
| `mark_as_unread()` | 标记未读 | `entry_id` |
| `delete_email()` | 删除邮件 | `entry_id` |
| `reply_email()` | 回复邮件 | `entry_id`, `body` |
| `forward_email()` | 转发邮件 | `entry_id`, `to` |

### 邮件搜索

```python
# 搜索主题包含 "项目" 的邮件
emails = Mail.search_emails("项目", limit=10)
for email in emails:
    print(f"来自: {email.sender}")
    print(f"主题: {email.subject}")
    print(f"时间: {email.time}")
    print()

# 获取最近 5 封收件箱邮件
recent = Mail.get_inbox(limit=5)
```

---

## 5. Outlook 日历自动化

### 基本用法

```python
from h_agent.skills.outlook import Calendar

# 创建 appointment（单次事件）
Calendar.create_appointment(
    subject="团队周会",
    start_time="2024-01-15 10:00",
    end_time="2024-01-15 11:00",
    location="会议室 A",
    body="请大家提前准备周报。",
)

# 创建全天事件
Calendar.create_all_day_event(
    subject="公司团建",
    date="2024-01-20",
    body="全天活动，请准时参加。"
)
```

### API 概览

| 方法 | 说明 | 参数 |
|------|------|------|
| `create_appointment()` | 创建 appointment | `subject`, `start_time`, `end_time`, `location`, `body` |
| `create_all_day_event()` | 创建全天事件 | `subject`, `date`, `body` |
| `get_calendar()` | 获取日历项 | `start_date`, `end_date`, `limit` |
| `update_appointment()` | 更新 appointment | `entry_id`, `**kwargs` |
| `delete_appointment()` | 删除 appointment | `entry_id` |
| `create_meeting()` | 创建会议（带邀请） | `subject`, `start`, `end`, `attendees` |

### 日历查询

```python
from datetime import datetime, timedelta

# 查询未来 7 天的事件
today = datetime.now()
next_week = today + timedelta(days=7)

events = Calendar.get_calendar(
    start_date=today.strftime("%Y-%m-%d"),
    end_date=next_week.strftime("%Y-%m-%d"),
    limit=20
)
for event in events:
    print(f"{event.start} - {event.subject}")
```

---

## 6. Outlook 联系人自动化

### 基本用法

```python
from h_agent.skills.outlook import Contacts

# 创建联系人
Contacts.create_contact(
    first_name="张三",
    last_name="李",
    email="zhangsan@example.com",
    phone="13800138000",
    company="示例公司",
    title="工程师"
)

# 搜索联系人
results = Contacts.search_contacts("张三")
for contact in results:
    print(f"{contact.full_name} - {contact.email}")
```

### API 概览

| 方法 | 说明 | 参数 |
|------|------|------|
| `create_contact()` | 创建联系人 | `first_name`, `last_name`, `email`, `phone`, `company` |
| `search_contacts()` | 搜索联系人 | `query` |
| `update_contact()` | 更新联系人 | `entry_id`, `**kwargs` |
| `delete_contact()` | 删除联系人 | `entry_id` |
| `create_contact_group()` | 创建联系人组 | `name`, `members` |

---

## 7. 错误处理

```python
from h_agent.skills.office import Word
from h_agent.skills.outlook import Mail
import pywintypes

try:
    # 所有操作
    doc = Word.open_document("nonexistent.docx")
except FileNotFoundError:
    print("文件不存在")
except pywintypes.com_error as e:
    print(f"COM 错误: {e}")
except OSError as e:
    # 非 Windows 平台
    print(f"仅支持 Windows: {e}")
```

---

## 8. 注意事项

- **仅 Windows**：导入时如果不是 Windows 会立即抛出 `OSError`
- **Outlook 运行**：发送邮件需要 Outlook 客户端在后台运行
- **COM 依赖**：使用 `pywin32`，部分企业环境可能有 COM 权限限制
- **文件路径**：Windows 路径支持中文，但建议使用 raw string 或正斜杠
- **后台进程**：`pywin32` 操作 Office 时 Office 会以隐藏窗口运行
- **保存前关闭**：打开已有文件前确保已保存，否则会提示覆盖确认
