# ADR-0007：License 与公开发布策略

- 状态：Accepted
- 日期：2026-11-17

## 背景

项目确定通过公开 Git 仓库提供完整源码，用户可以直接 clone 使用。项目采用 Apache-2.0。

## 提案

- Git 仓库作为首要分发渠道，版本由 tag 和 commit SHA 标识。
- 仓库根目录的 LICENSE、README 和 pyproject 元数据必须保持一致。
- 在许可证确定前，不宣称用户可以再分发、修改或商业使用。
- 在对外发布、接受外部贡献或分发二进制前，确认 License、版权声明、第三方引用和贡献条款。
- README 与 pyproject 的 License 元数据必须与最终 LICENSE 文件一致。

## 待决

用户已确认项目完全开源并采用 Apache-2.0。发布前仍需补齐版权声明、第三方引用和贡献条款。
