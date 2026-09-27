// 统一 API 响应类型
export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T | null;
  request_id: string;
}

// 分页数据
export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// 分页查询参数
export interface PaginationParams {
  page?: number;
  page_size?: number;
}
