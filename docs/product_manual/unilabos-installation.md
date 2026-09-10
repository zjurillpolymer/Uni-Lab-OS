# 设备包规范与系统启动

:::{admonition} 阅读角色
- **业务负责人**：确认设备、物料、工艺流程、现场约束和设备包交付范围。
- **开发人员**：完成工作区、设备、物料、启动图和工作流定义。
- **验收人员**：按章节顺序检查设备包、模拟启动、异常路径和真机边界。
:::

本目录面向负责设备包开发、设备联调和实验流程配置的人员。文档按照“准备工作区 → 接入设备 → 定义物料 → 编写启动文件 → 编写工作流”的顺序组织，完成从设备包目录准备到模拟启动的全过程。

> **推荐阅读顺序：** 先了解工作区和设备包组成结构，再根据设备控制方式选择接入模板；随后定义物料、编写启动图（Graph JSON），最后完成实验操作（子工作流）和完整工作流。

```{toctree}
:maxdepth: 1

workspace
device-template
material-template
startup-files
workflow
```

## 工作区（设备包组成结构）

工作区是设备包项目的根目录，用于统一保存包描述文件、设备接入代码、物料定义、启动图、工作流和测试。

## 1. 设备接入模板

- [设备模板库与类别选择](template-library.md)
- [通用规范](generic-device.md)
- [PLC 控制的工站](plc-station.md)
- [串口／网络连接](serial-network.md)
- [上位机 API 接入](host-api.md)
- [鼠标模拟点击（可选）](mouse-automation.md)

## 2. 物料定义模板

- [工作站台面与仓库](deck-warehouse.md)
- [光电堆栈与旋转堆栈：物料 + 设备](stack.md)
- [孔板与吸头盒（Plate／Tiprack）](plate-tiprack.md)
- [容器（Container）](container-template.md)
- [小瓶载架](vial-rack.md)
- [弹夹](magazine.md)
- [其他可追踪物料](other-materials.md)

## 3. 启动文件

编写 `启动图`，声明设备实例、物料库位、连接参数和启动模式；模拟环境和真实环境应使用不同配置。

## 4. 工作流运行

包括可复用的实验操作（子工作流）和完整工作流的编写。工作流只调用已登记的设备动作和物料资源，并在 `package.yaml` 中登记唯一的 `workflow_uuid` 与源文件。
