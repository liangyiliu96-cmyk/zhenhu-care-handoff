"""路由包初始化。合并迁入。

提供 admission(入院)、discharge(出院)、monitoring(监测) 和 admin(管理) 四组路由,
全部挂载 UnifiedResponse 格式, 由 middleware 统一处理 request_id 和异常。
"""
