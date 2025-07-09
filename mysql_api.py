
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import mysql.connector
from flask_cors import CORS  # 导入CORS模块
from yzh_warehouse.config.config import DB_CONFIG
from yzh_warehouse.config.config import ip
from mysql.connector import Error

app = Flask(__name__)
CORS(app)  # 启用CORS，允许所有域名跨域访问

DB_CONFIG = DB_CONFIG

class MySQLConnection:
    def __init__(self):
        self.connection = mysql.connector.connect(
            host=ip,
            user="root",
            password="Iruance_99!@#",
            database="yzh_repertory01"
        )
        self.current_user = None

    def __del__(self):
        if self.connection.is_connected():
            self.connection.close()

    def zhixin_sql(self, sql, params=None, fetch_all=True):
        """执行SQL语句并返回结果"""
        try:
            with self.connection.cursor(dictionary=True, buffered=True) as cursor:
                cursor.execute(sql, params or ())

                # 对查询类语句返回结果集
                if sql.strip().lower().startswith(('select', 'show', 'describe', 'explain')):
                    return cursor.fetchall() if fetch_all else cursor.fetchone()

                # 对修改类语句返回受影响行数或自增ID
                elif sql.strip().lower().startswith(('insert', 'update', 'delete', 'replace')):
                    self.connection.commit()
                    if cursor.lastrowid:  # 针对INSERT返回自增ID
                        return cursor.lastrowid
                    return cursor.rowcount  # 返回受影响的行数

                # 对DDL语句直接提交
                else:
                    self.connection.commit()
                    return True  # 表示执行成功

        except Error as e:
            print(f"数据库错误: {e}")
            self.connection.rollback()
            return False  # 执行失败

# Mysql = MySQLConnection()
# print(Mysql.zhixin_sql('SHOW TABLES'),"&"*50)

def get_status_count(status):
    """统计指定状态的设备数量"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        query = "SELECT COUNT(*) as count FROM repertory01 WHERE status = %s"
        cursor.execute(query, (status,))
        result = cursor.fetchone()
        return result['count'] if result else 0
    except Exception as e:
        print(f"统计状态错误: {e}")
        return 0
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/ping')
def ping():
    return jsonify({'message': 'pong'})

# 获取设备列表（分页）
@app.route('/api/devices', methods=['GET'])
def get_devices():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 10))
    offset = (page - 1) * page_size

    print(f"请求参数: page={page}, page_size={page_size}")

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        print("数据库连接成功")

        # 查询设备数据
        query = "SELECT * FROM repertory01 ORDER BY id DESC LIMIT %s OFFSET %s"
        cursor.execute(query, (page_size, offset))
        devices = cursor.fetchall()

        print(f"查询到 {len(devices)} 条记录")

        # 查询总记录数
        cursor.execute("SELECT COUNT(*) as total FROM repertory01")
        total = cursor.fetchone()['total']

        # 查询统计数据
        stats = {
            'total': total,
            'normal': get_status_count('正常'),
            'maintenance': get_status_count('待检修'),
            'damaged': get_status_count('已损坏')
        }

        print(f"统计数据: {stats}")

        return jsonify({
            'success': True,
            'devices': devices,
            'total': total,
            'stats': stats
        })

    except Exception as e:
        print(f"错误: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

#添加设备
@app.route('/api/add_devices', methods=['POST'])
def add_device():
    data = request.get_json()

    # 处理日期格式
    if 'warehouse_entry_time' in data:
        try:
            # 尝试解析ISO格式
            dt = datetime.fromisoformat(data['warehouse_entry_time'].replace('Z', '+00:00'))
            data['warehouse_entry_time'] = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass  # 保持原样
    else:
        data['warehouse_entry_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 验证inventory是否为整数
    if 'inventory' in data:
        try:
            data['inventory'] = int(data['inventory'])
        except ValueError:
            return jsonify({
                'success': False,
                'message': '参数类型错误: inventory必须为整数'
            }), 400

    # 验证product_unm是否为整数
    if 'product_unm' in data and data['product_unm'] != '':
        try:
            data['product_unm'] = int(data['product_unm'])
        except ValueError:
            return jsonify({
                'success': False,
                'message': '参数类型错误: product_unm必须为整数'
            }), 400
    else:
        data['product_unm'] = None

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        sql = """
        INSERT INTO repertory01
        (devices_name, warehouse_entry_time, inventory, status, product_unm, operate, particulars)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        val = (
            data['devices_name'],
            data['warehouse_entry_time'],
            data['inventory'],
            data['status'],
            data['product_unm'],
            data.get('operate', ''),
            data.get('particulars', '')
        )

        cursor.execute(sql, val)
        conn.commit()

        return jsonify({
            'success': True,
            'message': '设备添加成功'
        })

    except mysql.connector.Error as err:
        print(f"数据库错误: {err}")
        conn.rollback()
        return jsonify({
            'success': False,
            'message': f"数据库错误: {err.msg}"
        }), 500
    except Exception as e:
        print(f"未知错误: {e}")
        conn.rollback()
        return jsonify({
            'success': False,
            'message': f"未知错误: {str(e)}"
        }), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
# 删除设备
@app.route('/api/del_devices/<int:device_id>', methods=['DELETE'])
def delete_device(device_id):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # 删除数据
        sql = "DELETE FROM repertory01 WHERE id = %s"
        cursor.execute(sql, (device_id,))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({
                'success': False,
                'message': '设备不存在'
            }), 404

        return jsonify({
            'success': True,
            'message': '设备删除成功'
        })

    except Exception as e:
        conn.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


#获取入库记录
@app.route('/api/warehouse_records', methods=['GET'])
def get_warehouse_records():
    """获取入库记录"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        # 查询入库记录（按入库时间降序）
        query = """
SELECT * FROM repertory01 WHERE warehouse_entry_time BETWEEN '2025-07-01' AND '2025-07-07';
        """
        cursor.execute(query)
        records = cursor.fetchall()

        # 格式化日期
        for record in records:
            if record['warehouse_entry_time']:
                record['warehouse_entry_time'] = record['warehouse_entry_time'].strftime("%Y-%m-%d %H:%M:%S")

        return jsonify({
            'success': True,
            'records': records
        })

    except Exception as e:
        print(f"错误: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

# 获取出库记录
@app.route('/api/out_records', methods=['GET'])
def get_out_records():
    try:
        Mysql = MySQLConnection()

        # 查询设备名称
        query = 'SELECT device_name FROM chuku_data'
        device_result = Mysql.zhixin_sql(query, fetch_all=False)
        print(device_result,"*"*30)

        if not device_result:
            return jsonify({'success': False, 'message': '未找到设备记录'})

        device_name = device_result['device_name']  # 使用字典格式获取结果

        # 插入新记录（使用参数化查询）
        insert_sql = """
        INSERT INTO chuku_data (
            operator, device_name, chuku_unm, 
            device_number, destination, recipient
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = ('小新', device_name, 26, 44, '北京11', '北京饭334')

        Mysql.zhixin_sql(insert_sql, params)

        # 返回所有记录
        data = Mysql.zhixin_sql('SELECT * FROM chuku_data')

        return jsonify({
            'success': True,
            'data': data,
            'message': '插入成功'
        })

    except Exception as e:
        print(f"错误: {e}")
        return jsonify({
            'success': False,
            'message': '操作失败，请稍后重试'
        }), 500

#获取库存表数量
@app.route('/api/table_count', methods=['GET'])
def get_table_count():
    """获取库存表数量"""
    try:
        Mysql = MySQLConnection()

        # 查询设备名称
        query = 'SHOW TABLES'
        device_result = Mysql.zhixin_sql(query, fetch_all=True)

        if not device_result:
            return jsonify({'success': False, 'message': '未找到设备记录'})

        list1 = []
        for i in device_result:
            # print(i.get('Tables_in_yzh_repertory01'))
            list1.append(i.get('Tables_in_yzh_repertory01'))
        return jsonify({
            'success': True,
            'data': list1,
            'message': '查询成功'
        })

    except Exception as e:
        print(f"错误: {e}")
        return jsonify({
            'success': False,
            'message': '操作失败，请稍后重试'})

#编辑设备数据
@app.route('/api/update_device/<int:device_id>', methods=['PUT'])
def update_device(device_id):
    """更新设备信息"""
    data = request.get_json()

    # 处理日期格式
    if 'warehouse_entry_time' in data:
        try:
            dt = datetime.fromisoformat(data['warehouse_entry_time'].replace('Z', '+00:00'))
            data['warehouse_entry_time'] = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    # 验证inventory是否为整数
    if 'inventory' in data:
        try:
            data['inventory'] = int(data['inventory'])
        except ValueError:
            return jsonify({'success': False, 'message': 'inventory必须为整数'}), 400

    # 验证product_unm是否为整数
    if 'product_unm' in data and data['product_unm'] != '':
        try:
            data['product_unm'] = int(data['product_unm'])
        except ValueError:
            return jsonify({'success': False, 'message': 'product_unm必须为整数'}), 400
    else:
        data['product_unm'] = None

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # 修复SQL参数不匹配问题
        sql = """
        UPDATE repertory01
        SET devices_name = %s, 
            warehouse_entry_time = %s, 
            inventory = %s, 
            status = %s, 
            product_unm = %s, 
            operate = %s, 
            particulars = %s
        WHERE id = %s
        """
        val = (
            data['devices_name'],
            data['warehouse_entry_time'],
            data['inventory'],
            data['status'],
            data['product_unm'],
            data.get('operate', ''),
            data.get('particulars', ''),
            device_id  # 添加设备ID作为最后一个参数
        )

        cursor.execute(sql, val)
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': '设备不存在'}), 404

        return jsonify({'success': True, 'message': '设备更新成功'})

    except mysql.connector.Error as err:
        print(f"数据库错误: {err}")
        conn.rollback()
        return jsonify({'success': False, 'message': f"数据库错误: {err.msg}"}), 500
    except Exception as e:
        print(f"未知错误: {e}")
        conn.rollback()
        return jsonify({'success': False, 'message': f"未知错误: {str(e)}"}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


#添加仓库的表
@app.route('/api/add_warehouse', methods=['POST'])
def add_warehouse():
    """添加新仓库表"""
    data = request.get_json()

    # 验证必要参数
    if not data or 'warehouse_name' not in data:
        return jsonify({
            'success': False,
            'message': '缺少必要参数: warehouse_name'
        }), 400

    warehouse_name = data['warehouse_name']

    try:
        Mysql = MySQLConnection()

        # 创建新表SQL
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {warehouse_name} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            devices_name VARCHAR(255) NOT NULL,
            warehouse_entry_time DATETIME,
            inventory INT,
            status VARCHAR(50),
            product_unm INT,
            operate VARCHAR(255),
            particulars TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        # 执行创建表
        result = Mysql.zhixin_sql(create_table_sql)

        if result:
            return jsonify({
                'success': True,
                'message': f'仓库表 {warehouse_name} 创建成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '创建仓库表失败'
            }), 500

    except Exception as e:
        print(f"错误: {e}")
        return jsonify({
            'success': False,
            'message': f'创建仓库表失败: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)