import { useState, useEffect } from 'react'
import mqtt from 'mqtt'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { FaShieldAlt, FaCarSide, FaHistory, FaCogs, FaBrain, FaMicrochip } from 'react-icons/fa'

function App() {
  const [distanceData, setDistanceData] = useState([]);
  const [currentDistance, setCurrentDistance] = useState(0);
  const [aiStatus, setAiStatus] = useState('WAITING');
  const [gateStatus, setGateStatus] = useState('UNKNOWN');
  const [alerts, setAlerts] = useState([]);
  const [mode, setMode] = useState('AUTO'); // AUTO or MANUAL
  const [dangerThreshold, setDangerThreshold] = useState(60);
  const [mqttClient, setMqttClient] = useState(null);
  const [aiEngine, setAiEngine] = useState('local'); // 'local' or 'gemini'

  const MQTT_BROKER = 'wss://broker.emqx.io:8084/mqtt';

  useEffect(() => {
    // 1. Connect MQTT
    const client = mqtt.connect(MQTT_BROKER);
    setMqttClient(client);

    client.on('connect', () => {
      console.log('Connected to MQTT Broker via WebSockets');
      client.subscribe('barrier/distance');
      client.subscribe('barrier/ai_status');
      client.subscribe('barrier/ai_mode/ack');
    });

    client.on('message', (topic, message) => {
      const payload = JSON.parse(message.toString());
      if (topic === 'barrier/distance') {
        const { distance, timestamp } = payload;
        setCurrentDistance(distance);
        setDistanceData(prev => {
          const newData = [...prev, { time: new Date(timestamp).toLocaleTimeString(), distance }];
          // Keep last 30 data points
          return newData.length > 30 ? newData.slice(newData.length - 30) : newData;
        });
      } else if (topic === 'barrier/ai_status') {
        const status = payload.status;
        setAiStatus(status);
        if (mode === 'AUTO') {
          if (status === 'FAST_APPROACH' || status === 'LINGERING') {
            setGateStatus('CLOSED');
          } else if (status === 'APPROACHING' || status === 'MOVING_AWAY') {
            setGateStatus('OPEN');
          }
        }
      } else if (topic === 'barrier/ai_mode/ack') {
        setAiEngine(payload.active_mode);
      }
    });

    return () => client.end();
  }, [mode]);

  useEffect(() => {
    // Poll alerts every 2 seconds
    const fetchAlerts = async () => {
      try {
        const res = await axios.get('http://localhost:8000/api/alerts');
        setAlerts(res.data);
      } catch (err) {
        console.error("Failed to fetch alerts", err);
      }
    }
    fetchAlerts();
    const inv = setInterval(fetchAlerts, 2000);
    return () => clearInterval(inv);
  }, []);

  const getStatusColor = (status) => {
    switch (status) {
      case 'FAST_APPROACH': return 'text-red-500 shadow-[0_0_15px_rgba(239,68,68,0.5)]';
      case 'LINGERING': return 'text-orange-500 shadow-[0_0_15px_rgba(249,115,22,0.5)]';
      case 'APPROACHING': return 'text-blue-400';
      case 'MOVING_AWAY': return 'text-green-400';
      default: return 'text-gray-400';
    }
  };

  const getGateColor = () => {
    return gateStatus === 'OPEN' ? 'text-green-500 border-green-500' : 
           gateStatus === 'CLOSED' ? 'text-red-500 border-red-500' : 'text-gray-500 border-gray-500';
  }

  const handleThresholdChange = (e) => {
    const val = parseInt(e.target.value);
    setDangerThreshold(val);
    if (mqttClient) {
      mqttClient.publish('barrier/config', JSON.stringify({ danger_threshold: val }));
    }
  };

  const handleEngineSwitch = (engine) => {
    setAiEngine(engine);
    if (mqttClient) {
      mqttClient.publish('barrier/ai_mode', JSON.stringify({ mode: engine }));
    }
  };

  const handleManualControl = (status) => {
    setGateStatus(status);
    if (mqttClient) {
      mqttClient.publish('barrier/control', JSON.stringify({ command: status }));
    }
  };

  const getEngineBadge = (engine) => {
    if (engine === 'gemini') {
      return <span className="inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30"><FaBrain className="text-[10px]" /> Gemini</span>;
    }
    return <span className="inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"><FaMicrochip className="text-[10px]" /> Local</span>;
  };

  return (
    <div className="min-h-screen bg-[#020617] text-white p-8 font-sans transition-colors duration-500">
      
      {/* Header */}
      <header className="flex items-center justify-between mb-10 pb-6 border-b border-white/10">
        <div className="flex items-center gap-4">
          <div className="bg-gradient-to-br from-indigo-500 to-purple-600 p-3 rounded-2xl shadow-lg border border-white/10">
            <FaShieldAlt className="text-3xl text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-400">
              Sentinel Barrier
            </h1>
            <p className="text-slate-400 text-sm mt-1">Smart Proximity Detection AI</p>
          </div>
        </div>
        
        <div className="flex gap-3 items-center">
          {/* AI Engine Toggle */}
          <div className="flex items-center bg-slate-800/70 border border-white/10 rounded-full p-1 gap-1">
            <button
              onClick={() => handleEngineSwitch('local')}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-bold transition-all ${
                aiEngine === 'local' ? 'bg-cyan-600 text-white shadow' : 'text-slate-400 hover:text-white'
              }`}
            >
              <FaMicrochip /> Local AI
            </button>
            <button
              onClick={() => handleEngineSwitch('gemini')}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-bold transition-all ${
                aiEngine === 'gemini' ? 'bg-purple-600 text-white shadow' : 'text-slate-400 hover:text-white'
              }`}
            >
              <FaBrain /> Gemini AI
            </button>
          </div>

          {/* Barrier Mode Toggle */}
          <button 
            onClick={() => setMode(mode === 'AUTO' ? 'MANUAL' : 'AUTO')}
            className={`px-6 py-2 rounded-full font-bold text-sm transition-all shadow-lg ${mode === 'AUTO' ? 'bg-indigo-600 text-white hover:bg-indigo-500' : 'bg-slate-800 text-white border border-slate-600'}`}
          >
            {mode === 'AUTO' ? 'Auto Mode' : 'Manual Mode'}
          </button>
        </div>
      </header>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Column: Live Stats */}
        <div className="lg:col-span-1 space-y-8">
           {/* Current Target Stats */}
           <div className="relative group bg-slate-900/50 backdrop-blur-xl border border-white/10 rounded-3xl p-8 shadow-2xl overflow-hidden hover:bg-slate-800/60 transition-all">
             <div className="absolute top-0 right-0 p-3 opacity-20 group-hover:opacity-40 transition-opacity">
                <FaCarSide className="text-6xl" />
             </div>
             <h2 className="text-slate-400 text-lg font-medium mb-2 uppercase tracking-wide">Target Distance</h2>
             <div className="flex items-baseline gap-2">
                <span className="text-7xl font-black text-white">{currentDistance.toFixed(1)}</span>
                <span className="text-2xl text-slate-500 font-medium tracking-tighter">cm</span>
             </div>
             
             <div className="mt-8">
               <div className="flex items-center justify-between mb-3">
                 <h3 className="text-slate-400 text-sm font-medium uppercase tracking-wide">AI Classification</h3>
                 {getEngineBadge(aiEngine)}
               </div>
               <div className={`px-4 py-2 rounded-lg border border-white/5 bg-black/40 font-bold tracking-widest text-lg w-max transition-all duration-300 ${getStatusColor(aiStatus)}`}>
                 {aiStatus}
               </div>
               {aiEngine === 'gemini' && (
                 <p className="text-xs text-purple-400/70 mt-2">Powered by Google Gemini 1.5 Flash</p>
               )}
             </div>
           </div>

           {/* Barrier State */}
           <div className="bg-slate-900/50 backdrop-blur-xl border border-white/10 rounded-3xl p-8 shadow-2xl">
              <h2 className="text-slate-400 text-lg font-medium mb-6 uppercase tracking-wide">Barrier Control</h2>
              <div className="flex items-center justify-center py-6">
                 <div className={`text-4xl font-black border-4 rounded-full w-48 h-48 flex items-center justify-center transition-all duration-500 shadow-2xl ${getGateColor()}`}>
                   {gateStatus}
                 </div>
              </div>
              
              {mode === 'MANUAL' && (
                <div className="mt-6 flex justify-center gap-4">
                  <button 
                    onClick={() => handleManualControl('OPEN')} 
                    className="px-6 py-3 bg-green-600/20 text-green-400 rounded-xl hover:bg-green-600/40 border border-green-500/30 font-bold transition-all"
                  >
                    Force Open
                  </button>
                  <button 
                    onClick={() => handleManualControl('CLOSED')} 
                    className="px-6 py-3 bg-red-600/20 text-red-500 rounded-xl hover:bg-red-600/40 border border-red-500/30 font-bold transition-all"
                  >
                    Force Close
                  </button>
                </div>
              )}
           </div>

           {/* Settings */}
           <div className="bg-slate-900/50 backdrop-blur-xl border border-white/10 rounded-3xl p-8 shadow-2xl">
              <h2 className="text-slate-400 text-lg font-medium mb-6 uppercase tracking-wide flex items-center gap-2">
                 <FaCogs /> Configuration
              </h2>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-slate-400">Danger Threshold</span>
                    <span className="text-white font-bold">{dangerThreshold} cm</span>
                  </div>
                  <input 
                    type="range" 
                    min="10" 
                    max="150" 
                    value={dangerThreshold}
                    onChange={handleThresholdChange}
                    className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                  />
                  <p className="text-xs text-slate-500 mt-2">Objects closer than this limit will trigger a LINGERING or FAST_APPROACH alert.</p>
                </div>
              </div>
           </div>
        </div>

        {/* Right Column: Chart & History */}
        <div className="lg:col-span-2 space-y-8">
            
            {/* Live Chart */}
            <div className="bg-slate-900/50 backdrop-blur-xl border border-white/10 rounded-3xl p-6 shadow-2xl h-[400px] flex flex-col">
              <h2 className="text-slate-300 font-medium mb-6 uppercase tracking-wide flex items-center gap-2">
                 <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
                 Live Realmetry
              </h2>
              <div className="flex-1 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={distanceData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                    <XAxis dataKey="time" stroke="#64748b" tick={{fontSize: 12}} />
                    <YAxis stroke="#64748b" domain={[0, 200]} tick={{fontSize: 12}} />
                    <Tooltip 
                      contentStyle={{backgroundColor: '#1e293b', border: 'none', borderRadius: '12px', color: '#fff'}}
                      itemStyle={{color: '#60a5fa', fontWeight: 'bold'}}
                    />
                    <Line type="monotone" dataKey="distance" stroke="#60a5fa" strokeWidth={4} dot={false} activeDot={{r: 8, fill: '#3b82f6'}} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Alert History */}
            <div className="bg-slate-900/50 backdrop-blur-xl border border-white/10 rounded-3xl p-6 shadow-2xl">
              <h2 className="text-slate-300 font-medium mb-6 uppercase tracking-wide flex items-center gap-2">
                 <FaHistory /> Incident Log
              </h2>
              
              {alerts.length === 0 ? (
                <div className="text-slate-500 text-center py-6">No recent alerts recorded.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm text-slate-300">
                    <thead className="bg-slate-800/50 text-slate-400">
                      <tr>
                        <th className="px-4 py-3 rounded-tl-lg">Time</th>
                        <th className="px-4 py-3">Event</th>
                        <th className="px-4 py-3">Distance</th>
                        <th className="px-4 py-3 rounded-tr-lg">Engine</th>
                      </tr>
                    </thead>
                    <tbody>
                      {alerts.map((alert) => (
                        <tr key={alert.id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                          <td className="px-4 py-3">{new Date(alert.timestamp).toLocaleTimeString()}</td>
                          <td className={`px-4 py-3 font-bold ${getStatusColor(alert.status)}`}>{alert.status}</td>
                          <td className="px-4 py-3">{alert.distance} cm</td>
                          <td className="px-4 py-3">{getEngineBadge(alert.ai_engine || 'local')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

        </div>
      </div>
    </div>
  )
}

export default App
