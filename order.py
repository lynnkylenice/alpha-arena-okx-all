import ccxt
import os
import time
from datetime import datetime, timedelta
from data_manager import update_system_status, save_trade_record
# 初始化OKX交易所
exchange = ccxt.okx({
    'options': {
        'defaultType': 'swap',  # OKX使用swap表示永续合约
    },
    'apiKey': os.getenv('OKX_API_KEY'),
    'secret': os.getenv('OKX_SECRET'),
    'password': os.getenv('OKX_PASSWORD'),  # OKX需要交易密码
})

# 交易参数配置 - 结合两个版本的优点
TRADE_CONFIG = {
    'symbol': 'BTC/USDT:USDT',  # OKX的合约符号格式
    'leverage': 10,  # 杠杆倍数,只影响保证金不影响下单价值
    'timeframe': '15m',  # 使用15分钟K线
    'test_mode': False,  # 测试模式
    'data_points': 96,  # 24小时数据（96根15分钟K线）
    'analysis_periods': {
        'short_term': 20,  # 短期均线
        'medium_term': 50,  # 中期均线
        'long_term': 96  # 长期趋势
    },
    # 新增智能仓位参数
    'position_management': {
        'enable_intelligent_position': True,  # 🆕 新增：是否启用智能仓位管理
        'base_usdt_amount': 100,  # USDT投入下单基数
        'high_confidence_multiplier': 1.5,
        'medium_confidence_multiplier': 1.0,
        'low_confidence_multiplier': 0.5,
        'max_position_ratio': 50,  # 单次最大仓位比例
        'trend_strength_multiplier': 1.2
    }
}


def get_current_position():
    """获取当前持仓情况 - OKX版本"""
    try:
        positions = exchange.fetch_positions([TRADE_CONFIG['symbol']])

        for pos in positions:
            if pos['symbol'] == TRADE_CONFIG['symbol']:
                contracts = float(pos['contracts']) if pos['contracts'] else 0

                if contracts > 0:
                    return {
                        'side': pos['side'],  # 'long' or 'short'
                        'size': contracts,
                        'entry_price': float(pos['entryPrice']) if pos['entryPrice'] else 0,
                        'unrealized_pnl': float(pos['unrealizedPnl']) if pos['unrealizedPnl'] else 0,
                        'leverage': float(pos['leverage']) if pos['leverage'] else TRADE_CONFIG['leverage'],
                        'symbol': pos['symbol']
                    }

        return None

    except Exception as e:
        print(f"获取持仓失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def calculate_intelligent_position(signal_data, price_data, current_position):
    """计算智能仓位大小 - 修复版"""
    config = TRADE_CONFIG['position_management']

    # 🆕 新增：如果禁用智能仓位，使用固定仓位
    if not config.get('enable_intelligent_position', True):
        fixed_contracts = 0.1  # 固定仓位大小，可以根据需要调整
        print(f"🔧 智能仓位已禁用，使用固定仓位: {fixed_contracts} 张")
        return fixed_contracts

    try:
        # 获取账户余额
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']

        # 基础USDT投入
        base_usdt = config['base_usdt_amount']
        print(f"💰 可用USDT余额: {usdt_balance:.2f}, 下单基数{base_usdt}")

        # 根据信心程度调整 - 修复这里
        confidence_multiplier = {
            'HIGH': config['high_confidence_multiplier'],
            'MEDIUM': config['medium_confidence_multiplier'],
            'LOW': config['low_confidence_multiplier']
        }.get(signal_data['confidence'], 1.0)  # 添加默认值

        # 根据趋势强度调整
        trend = price_data['trend_analysis'].get('overall', '震荡整理')
        if trend in ['强势上涨', '强势下跌']:
            trend_multiplier = config['trend_strength_multiplier']
        else:
            trend_multiplier = 1.0

        # 根据RSI状态调整（超买超卖区域减仓）
        rsi = price_data['technical_data'].get('rsi', 50)
        if rsi > 75 or rsi < 25:
            rsi_multiplier = 0.7
        else:
            rsi_multiplier = 1.0

        # 计算建议投入USDT金额
        suggested_usdt = base_usdt * confidence_multiplier * trend_multiplier * rsi_multiplier

        # 风险管理：不超过总资金的指定比例 - 删除重复定义
        max_usdt = usdt_balance * config['max_position_ratio']
        final_usdt = min(suggested_usdt, max_usdt)

        # 正确的合约张数计算！
        # 公式：合约张数 = (投入USDT) / (当前价格 * 合约乘数)
        contract_size = (final_usdt) / (price_data['price'] * TRADE_CONFIG['contract_size'])

        print(f"📊 仓位计算详情:")
        print(f"   - 基础USDT: {base_usdt}")
        print(f"   - 信心倍数: {confidence_multiplier}")
        print(f"   - 趋势倍数: {trend_multiplier}")
        print(f"   - RSI倍数: {rsi_multiplier}")
        print(f"   - 建议USDT: {suggested_usdt:.2f}")
        print(f"   - 最终USDT: {final_usdt:.2f}")
        print(f"   - 合约乘数: {TRADE_CONFIG['contract_size']}")
        print(f"   - 计算合约: {contract_size:.4f} 张")

        # 精度处理：OKX BTC合约最小交易单位为0.01张
        contract_size = round(contract_size, 2)  # 保留2位小数

        # 确保最小交易量
        min_contracts = TRADE_CONFIG.get('min_amount', 0.01)
        if contract_size < min_contracts:
            contract_size = min_contracts
            print(f"⚠️ 仓位小于最小值，调整为: {contract_size} 张")

        print(f"🎯 最终仓位: {final_usdt:.2f} USDT → {contract_size:.2f} 张合约")
        return contract_size

    except Exception as e:
        print(f"❌ 仓位计算失败，使用基础仓位: {e}")
        # 紧急备用计算
        base_usdt = config['base_usdt_amount']
        contract_size = (base_usdt * TRADE_CONFIG['leverage']) / (
                    price_data['price'] * TRADE_CONFIG.get('contract_size', 0.01))
        return round(max(contract_size, TRADE_CONFIG.get('min_amount', 0.01)), 2)



def cancel_existing_tp_sl_orders():
    """取消现有的止盈止损订单"""
    global active_tp_sl_orders

    try:
        # 转换交易对格式：BTC/USDT:USDT -> BTC-USDT-SWAP
        inst_id = TRADE_CONFIG['symbol'].replace('/USDT:USDT', '-USDT-SWAP').replace('/', '-')

        # 使用OKX专用的算法订单API
        # 获取所有活跃的算法订单（止盈止损订单）
        try:
            # OKX的算法订单查询
            response = exchange.private_get_trade_orders_algo_pending({
                'instType': 'SWAP',
                'instId': inst_id,
                'ordType': 'conditional'  # 查询条件单
            })

            if response.get('code') == '0' and response.get('data'):
                for order in response['data']:
                    # 检查是否是止盈止损订单
                    ord_type = order.get('ordType')
                    if ord_type in ['conditional', 'oco']:
                        try:
                            # 取消算法订单
                            cancel_response = exchange.private_post_trade_cancel_algos({
                                'params': [{
                                    'algoId': order['algoId'],
                                    'instId': TRADE_CONFIG['symbol']
                                }]
                            })

                            if cancel_response.get('code') == '0':
                                print(f"✅ 已取消旧的止盈止损订单: {order['algoId']}")
                            else:
                                print(f"⚠️ 取消订单失败: {cancel_response.get('msg')}")
                        except Exception as e:
                            print(f"⚠️ 取消订单异常 {order.get('algoId')}: {e}")
        except Exception as e:
            print(f"⚠️ 查询算法订单失败: {e}")

        # 重置全局变量
        active_tp_sl_orders['take_profit_order_id'] = None
        active_tp_sl_orders['stop_loss_order_id'] = None

    except Exception as e:
        print(f"⚠️ 取消止盈止损订单时出错: {e}")


def execute_intelligent_trade(signal_data, price_data):
    """执行智能交易 - OKX版本（支持同方向加仓减仓）"""
    global position

    current_position = get_current_position()

    # 防止频繁反转的逻辑保持不变
    if current_position and signal_data != 'HOLD':
        current_side = current_position['side']  # 'long' 或 'short'

        if signal_data['signal'] == 'BUY':
            new_side = 'long'
        elif signal_data['signal'] == 'SELL':
            new_side = 'short'
        else:
            new_side = None

        # 如果方向相反，需要高信心才执行
        # if new_side != current_side:
        #     if signal_data['confidence'] != 'HIGH':
        #         print(f"🔒 非高信心反转信号，保持现有{current_side}仓")
        #         return

        #     if len(signal_history) >= 2:
        #         last_signals = [s['signal'] for s in signal_history[-2:]]
        #         if signal_data['signal'] in last_signals:
        #             print(f"🔒 近期已出现{signal_data['signal']}信号，避免频繁反转")
        #             return

    # 计算智能仓位
    position_size = calculate_intelligent_position(signal_data, price_data, current_position)

    print(f"交易信号: {signal_data['signal']}")
    print(f"信心程度: {signal_data['confidence']}")
    print(f"智能仓位: {position_size:.2f} 张")
    print(f"理由: {signal_data['reason']}")
    print(f"当前持仓: {current_position}")

    # 风险管理
    if signal_data['confidence'] == 'LOW' and not TRADE_CONFIG['test_mode']:
        print("⚠️ 低信心信号，跳过执行")
        return

    if TRADE_CONFIG['test_mode']:
        print("测试模式 - 仅模拟交易")
        return

    try:
        # 执行交易逻辑 - 支持同方向加仓减仓
        if signal_data['signal'] == 'BUY':
            if current_position and current_position['side'] == 'short':
                # 先检查空头持仓是否真实存在且数量正确
                if current_position['size'] > 0:
                    print(f"平空仓 {current_position['size']:.2f} 张并开多仓 {position_size:.2f} 张...")
                    # 取消现有的止盈止损订单
                    cancel_existing_tp_sl_orders()
                    # 平空仓
                    exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'buy',
                        current_position['size'],
                        params={'reduceOnly': True, 'tag': 'c314b0aecb5bBCDE'}
                    )
                    time.sleep(1)
                    # 开多仓
                    exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'buy',
                        position_size,
                        params={'tag': 'c314b0aecb5bBCDE'}
                    )
                else:
                    print("⚠️ 检测到空头持仓但数量为0，直接开多仓")
                    exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'buy',
                        position_size,
                        params={'tag': 'c314b0aecb5bBCDE'}
                    )

            elif current_position and current_position['side'] == 'long':
                # 同方向，检查是否需要调整仓位
                size_diff = position_size - current_position['size']

                if abs(size_diff) >= 0.01:  # 有可调整的差异
                    if size_diff > 0:
                        # 加仓
                        add_size = round(size_diff, 2)
                        print(
                            f"多仓加仓 {add_size:.2f} 张 (当前:{current_position['size']:.2f} → 目标:{position_size:.2f})")
                        exchange.create_market_order(
                            TRADE_CONFIG['symbol'],
                            'buy',
                            add_size,
                            params={'tag': 'c314b0aecb5bBCDE'}
                        )
                    else:
                        # 减仓
                        reduce_size = round(abs(size_diff), 2)
                        print(
                            f"多仓减仓 {reduce_size:.2f} 张 (当前:{current_position['size']:.2f} → 目标:{position_size:.2f})")
                        exchange.create_market_order(
                            TRADE_CONFIG['symbol'],
                            'sell',
                            reduce_size,
                            params={'reduceOnly': True, 'tag': 'c314b0aecb5bBCDE'}
                        )
                else:
                    print(
                        f"已有多头持仓，仓位合适保持现状 (当前:{current_position['size']:.2f}, 目标:{position_size:.2f})")
            else:
                # 无持仓时开多仓
                print(f"开多仓 {position_size:.2f} 张...")
                exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'buy',
                    position_size,
                    params={'tag': 'c314b0aecb5bBCDE'}
                )

        elif signal_data['signal'] == 'SELL':
            if current_position and current_position['side'] == 'long':
                # 先检查多头持仓是否真实存在且数量正确
                if current_position['size'] > 0:
                    print(f"平多仓 {current_position['size']:.2f} 张并开空仓 {position_size:.2f} 张...")
                    # 取消现有的止盈止损订单
                    cancel_existing_tp_sl_orders()
                    # 平多仓
                    exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'sell',
                        current_position['size'],
                        params={'reduceOnly': True, 'tag': 'c314b0aecb5bBCDE'}
                    )
                    time.sleep(1)
                    # 开空仓
                    exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'sell',
                        position_size,
                        params={'tag': 'c314b0aecb5bBCDE'}
                    )
                else:
                    print("⚠️ 检测到多头持仓但数量为0，直接开空仓")
                    exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'sell',
                        position_size,
                        params={'tag': 'c314b0aecb5bBCDE'}
                    )

            elif current_position and current_position['side'] == 'short':
                # 同方向，检查是否需要调整仓位
                size_diff = position_size - current_position['size']

                if abs(size_diff) >= 0.01:  # 有可调整的差异
                    if size_diff > 0:
                        # 加仓
                        add_size = round(size_diff, 2)
                        print(
                            f"空仓加仓 {add_size:.2f} 张 (当前:{current_position['size']:.2f} → 目标:{position_size:.2f})")
                        exchange.create_market_order(
                            TRADE_CONFIG['symbol'],
                            'sell',
                            add_size,
                            params={'tag': 'c314b0aecb5bBCDE'}
                        )
                    else:
                        # 减仓
                        reduce_size = round(abs(size_diff), 2)
                        print(
                            f"空仓减仓 {reduce_size:.2f} 张 (当前:{current_position['size']:.2f} → 目标:{position_size:.2f})")
                        exchange.create_market_order(
                            TRADE_CONFIG['symbol'],
                            'buy',
                            reduce_size,
                            params={'reduceOnly': True, 'tag': 'c314b0aecb5bBCDE'}
                        )
                else:
                    print(
                        f"已有空头持仓，仓位合适保持现状 (当前:{current_position['size']:.2f}, 目标:{position_size:.2f})")
            else:
                # 无持仓时开空仓
                print(f"开空仓 {position_size:.2f} 张...")
                exchange.create_market_order(
                    TRADE_CONFIG['symbol'],
                    'sell',
                    position_size,
                    params={'tag': 'c314b0aecb5bBCDE'}
                )

        elif signal_data['signal'] == 'HOLD':
            print("建议观望，不执行交易")
            # 如果有持仓，确保止盈止损订单存在
            if current_position and current_position['size'] > 0:
                stop_loss_price = signal_data.get('stop_loss')
                take_profit_price = signal_data.get('take_profit')

                # 检查是否需要更新止盈止损
                if stop_loss_price or take_profit_price:
                    print(f"\n📊 更新止盈止损订单:")
                    print(f"   止损价格: {stop_loss_price}")
                    print(f"   止盈价格: {take_profit_price}")

                    set_stop_loss_take_profit(
                        position_side=current_position['side'],
                        stop_loss_price=stop_loss_price,
                        take_profit_price=take_profit_price,
                        position_size=current_position['size']
                    )
            return

        print("智能交易执行成功")
        time.sleep(2)
        position = get_current_position()
        print(f"更新后持仓: {position}")

        # 设置止盈止损订单
        if position and position['size'] > 0:
            stop_loss_price = signal_data.get('stop_loss')
            take_profit_price = signal_data.get('take_profit')

            if stop_loss_price or take_profit_price:
                print(f"\n📊 设置止盈止损:")
                print(f"   止损价格: {stop_loss_price}")
                print(f"   止盈价格: {take_profit_price}")

                set_stop_loss_take_profit(
                    position_side=position['side'],
                    stop_loss_price=stop_loss_price,
                    take_profit_price=take_profit_price,
                    position_size=position['size']
                )

        # 保存交易记录
        try:
            # 计算实际盈亏（如果有持仓）
            pnl = 0
            if current_position and position:
                # 如果方向改变或平仓，计算盈亏
                if current_position['side'] != position.get('side'):
                    if current_position['side'] == 'long':
                        pnl = (price_data['price'] - current_position['entry_price']) * current_position[
                            'size'] * TRADE_CONFIG.get('contract_size', 0.01)
                    else:
                        pnl = (current_position['entry_price'] - price_data['price']) * current_position[
                            'size'] * TRADE_CONFIG.get('contract_size', 0.01)

            trade_record = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'signal': signal_data['signal'],
                'price': price_data['price'],
                'amount': position_size,
                'confidence': signal_data['confidence'],
                'reason': signal_data['reason'],
                'pnl': pnl
            }
            save_trade_record(trade_record)
            print("✅ 交易记录已保存")
        except Exception as e:
            print(f"保存交易记录失败: {e}")

    except Exception as e:
        print(f"交易执行失败: {e}")

        # 如果是持仓不存在的错误，尝试直接开新仓
        if "don't have any positions" in str(e):
            print("尝试直接开新仓...")
            try:
                if signal_data['signal'] == 'BUY':
                    exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'buy',
                        position_size,
                        params={'tag': 'c314b0aecb5bBCDE'}
                    )
                elif signal_data['signal'] == 'SELL':
                    exchange.create_market_order(
                        TRADE_CONFIG['symbol'],
                        'sell',
                        position_size,
                        params={'tag': 'c314b0aecb5bBCDE'}
                    )
                print("直接开仓成功")
            except Exception as e2:
                print(f"直接开仓也失败: {e2}")

        import traceback
        traceback.print_exc()



def set_stop_loss_take_profit(position_side, stop_loss_price, take_profit_price, position_size):
    """
    设置止盈止损订单 - 使用OKX算法订单API

    参数:
        position_side: 'long' 或 'short'
        stop_loss_price: 止损价格
        take_profit_price: 止盈价格
        position_size: 持仓数量
    """
    global active_tp_sl_orders

    try:
        # 转换交易对格式：BTC/USDT:USDT -> BTC-USDT-SWAP
        inst_id = TRADE_CONFIG['symbol'].replace('/USDT:USDT', '-USDT-SWAP').replace('/', '-')

        # 先取消现有的止盈止损订单
        cancel_existing_tp_sl_orders()

        # 确定订单方向（平仓方向与开仓相反）
        close_side = 'sell' if position_side == 'long' else 'buy'

        # 使用OKX的算法订单API设置止盈止损
        # 方法1: 使用单独的止损和止盈订单

        # 设置止损订单 (Stop Loss)
        if stop_loss_price:
            try:
                # 使用OKX的条件单API
                sl_params = {
                    'instId': inst_id,
                    'tdMode': 'cross',  # 全仓模式
                    'side': close_side,
                    'ordType': 'conditional',  # 条件单
                    'sz': str(position_size),
                    'slTriggerPx': str(stop_loss_price),  # 止损触发价
                    'slOrdPx': '-1',  # 市价单（-1表示市价）
                    'reduceOnly': 'true',  # 只减仓
                    'tag': 'c314b0aecb5bBCDE'  # 节点（默认，无需改动）
                }

                # 调用OKX的算法订单API
                response = exchange.private_post_trade_order_algo(sl_params)

                if response.get('code') == '0' and response.get('data'):
                    algo_id = response['data'][0]['algoId']
                    active_tp_sl_orders['stop_loss_order_id'] = algo_id
                    print(f"✅ 止损订单已设置: 触发价={stop_loss_price}, 订单ID={algo_id}")
                else:
                    print(f"❌ 设置止损订单失败: {response.get('msg')}")

            except Exception as e:
                print(f"❌ 设置止损订单失败: {e}")

        # 设置止盈订单 (Take Profit)
        if take_profit_price:
            try:
                # 使用OKX的条件单API
                tp_params = {
                    'instId': inst_id,
                    'tdMode': 'cross',  # 全仓模式
                    'side': close_side,
                    'ordType': 'conditional',  # 条件单
                    'sz': str(position_size),
                    'tpTriggerPx': str(take_profit_price),  # 止盈触发价
                    'tpOrdPx': '-1',  # 市价单（-1表示市价）
                    'reduceOnly': 'true',  # 只减仓
                    'tag': 'c314b0aecb5bBCDE'  # 节点（默认，无需改动）
                }

                # 调用OKX的算法订单API
                response = exchange.private_post_trade_order_algo(tp_params)

                if response.get('code') == '0' and response.get('data'):
                    algo_id = response['data'][0]['algoId']
                    active_tp_sl_orders['take_profit_order_id'] = algo_id
                    print(f"✅ 止盈订单已设置: 触发价={take_profit_price}, 订单ID={algo_id}")
                else:
                    print(f"❌ 设置止盈订单失败: {response.get('msg')}")

            except Exception as e:
                print(f"❌ 设置止盈订单失败: {e}")

        return True

    except Exception as e:
        print(f"❌ 设置止盈止损失败: {e}")
        return False


