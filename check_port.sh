#!/bin/bash
# Helper para gerenciar a porta 8765

PORT=8765

echo "🔍 Verificando porta $PORT..."
echo ""

# Verificar se a porta está em uso
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "⚠️  PORTA $PORT ESTÁ EM USO!"
    echo ""
    echo "📋 Processos usando a porta:"
    lsof -i :$PORT
    echo ""
    
    # Perguntar se quer matar
    read -p "❓ Deseja matar esses processos? (s/N): " resposta
    
    if [ "$resposta" = "s" ] || [ "$resposta" = "S" ]; then
        echo ""
        echo "🔪 Matando processos na porta $PORT..."
        sudo fuser -k $PORT/tcp
        sleep 1
        
        # Verificar novamente
        if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
            echo "❌ Ainda há processos na porta. Tentando com -9..."
            sudo kill -9 $(lsof -ti:$PORT)
        else
            echo "✅ Porta $PORT liberada!"
        fi
    else
        echo ""
        echo "💡 Para matar manualmente:"
        echo "   sudo fuser -k $PORT/tcp"
        echo "   ou"
        echo "   sudo kill -9 \$(lsof -ti:$PORT)"
    fi
else
    echo "✅ Porta $PORT está LIVRE!"
fi

echo ""